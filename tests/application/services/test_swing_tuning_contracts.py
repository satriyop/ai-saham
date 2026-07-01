from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
    summarize_swing_backtest_attribution,
)
from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
    parse_tuning_config_path,
    resolve_tuning_config_value,
    validate_tuning_target_paths,
)
from tests.application.services.swing_backtest_attribution_fixtures import (
    ObservationFixture,
    make_trade,
)


def test_tuning_readiness_plan_blocks_insufficient_sample():
    summary = summarize_swing_backtest_attribution(
        (make_trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),),
        (ObservationFixture(forward_return_pct=1.0),),
    )

    plan = build_tuning_readiness_plan(summary)

    assert plan.intent == "readiness_gate_for_future_tuning_only"
    assert plan.status == "INSUFFICIENT_SAMPLE"
    assert plan.can_propose_changes is False
    assert plan.allowed_evidence_scopes == ()
    assert plan.allowed_config_families == ()
    assert plan.target_count == 0
    assert plan.blocked_reasons == summary.sample_quality.notes
    assert "No AI proposal" in " ".join(plan.notes)


def test_tuning_readiness_plan_allows_candidate_scoped_targets():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(ObservationFixture(forward_return_pct=1.0) for _ in range(30)),
    )

    plan = build_tuning_readiness_plan(summary)

    assert plan.status == "CANDIDATE_ONLY"
    assert plan.can_propose_changes is True
    assert plan.allowed_evidence_scopes == ("screened_candidates",)
    assert plan.allowed_config_families == (
        "market_context",
        "risk",
        "setup",
        "signal",
        "signal_and_risk",
    )
    assert plan.target_count == 9
    assert plan.blocked_reasons == ()
    assert "portfolio outcome tuning is blocked" in " ".join(plan.notes)


def test_tuning_proposal_draft_blocks_insufficient_sample():
    summary = summarize_swing_backtest_attribution(
        (make_trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),),
        (ObservationFixture(forward_return_pct=1.0),),
    )

    draft = build_tuning_proposal_draft(summary)

    assert draft.intent == "dry_run_tuning_proposal_contract_only"
    assert draft.status == "BLOCKED"
    assert draft.readiness_status == "INSUFFICIENT_SAMPLE"
    assert draft.can_generate_yaml_diff is False
    assert draft.requires_human_review is True
    assert draft.candidate_changes == ()
    assert len(draft.rejected_changes) == len(DEFAULT_TUNING_TARGETS)
    assert {
        rejection.reason
        for rejection in draft.rejected_changes
    } == {"Readiness gate blocks tuning proposals."}
    assert "No AI proposal" in " ".join(draft.evidence_notes)


def test_tuning_proposal_draft_lists_candidate_ready_review_targets():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(ObservationFixture(forward_return_pct=1.0) for _ in range(30)),
    )

    draft = build_tuning_proposal_draft(summary)

    dimensions = {candidate.dimension for candidate in draft.candidate_changes}

    assert draft.status == "READY_FOR_HUMAN_REVIEW"
    assert draft.readiness_status == "CANDIDATE_ONLY"
    assert draft.can_generate_yaml_diff is False
    assert draft.requires_human_review is True
    assert dimensions == {
        "candidate_setup_match",
        "candidate_signal_strength",
        "candidate_signal_score_bucket",
        "candidate_signal_factor_bucket",
        "candidate_trade_setup_action",
        "setup_gate",
    }
    assert tuple(draft.candidate_changes) == tuple(
        sorted(
            draft.candidate_changes,
            key=lambda candidate: (
                candidate.priority,
                candidate.evidence_sample_count,
                candidate.dimension,
            ),
            reverse=True,
        )
    )
    assert all(candidate.evidence_buckets for candidate in draft.candidate_changes)
    assert all(candidate.priority > 0 for candidate in draft.candidate_changes)
    assert {
        candidate.evidence_strength
        for candidate in draft.candidate_changes
    } <= {"LOW", "MEDIUM", "HIGH"}
    assert all(
        candidate.evidence_sample_count >= summary.sample_quality.min_sample_size
        for candidate in draft.candidate_changes
    )
    assert {
        rejection.dimension
        for rejection in draft.rejected_changes
        if rejection.reason == "No attribution buckets are available for this dimension."
    } == {"candidate_risk_gate", "candidate_risk_status", "candidate_regime"}


def test_tuning_proposal_draft_computes_evidence_strength_and_spread():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(
            ObservationFixture(
                forward_return_pct=4.0 if i < 15 else -2.0,
                setup_match="MATCH" if i < 15 else "NO_MATCH",
                signal_score=75 if i < 15 else 40,
            )
            for i in range(30)
        ),
    )

    draft = build_tuning_proposal_draft(summary)
    by_dimension = {
        candidate.dimension: candidate
        for candidate in draft.candidate_changes
    }

    signal_score = by_dimension["candidate_signal_score_bucket"]

    assert signal_score.evidence_strength == "MEDIUM"
    assert signal_score.evidence_sample_count == 30
    assert signal_score.evidence_return_spread_pct == 6.0
    assert signal_score.priority == 290
    assert signal_score.evidence_buckets == (
        "HIGH_70_PLUS | n=15 | avg=+4.00%",
        "LOW_BELOW_45 | n=15 | avg=-2.00%",
    )


def test_tuning_config_diff_draft_blocks_insufficient_sample():
    summary = summarize_swing_backtest_attribution(
        (make_trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),),
        (ObservationFixture(forward_return_pct=1.0),),
    )

    draft = build_tuning_config_diff_draft(summary)

    assert draft.intent == "config_diff_schema_only_no_apply"
    assert draft.status == "BLOCKED"
    assert draft.proposal_status == "BLOCKED"
    assert draft.can_apply is False
    assert draft.requires_human_review is True
    assert draft.diff_items == ()
    assert len(draft.rejected_items) == len(DEFAULT_TUNING_TARGETS)
    assert {
        rejection.reason
        for rejection in draft.rejected_items
    } == {"Proposal target rejected: Readiness gate blocks tuning proposals."}
    assert "read-only" in " ".join(draft.notes)


def test_tuning_config_diff_draft_is_schema_only_for_ready_proposals():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(
            ObservationFixture(
                forward_return_pct=4.0 if i < 15 else -2.0,
                setup_match="MATCH" if i < 15 else "NO_MATCH",
                signal_score=75 if i < 15 else 40,
            )
            for i in range(30)
        ),
    )

    draft = build_tuning_config_diff_draft(summary)

    assert draft.status == "READ_ONLY_VALUES"
    assert draft.proposal_status == "READY_FOR_HUMAN_REVIEW"
    assert draft.can_apply is False
    assert draft.diff_items
    assert draft.rejected_items
    assert {
        item.status
        for item in draft.diff_items
    } == {"CURRENT_VALUE_ONLY"}
    assert {
        item.confidence
        for item in draft.diff_items
    } == {"READ_ONLY_CURRENT_VALUE"}
    assert all(item.current_value is not None for item in draft.diff_items)
    assert all(item.proposed_value is None for item in draft.diff_items)
    assert all(item.parsed_target_path is not None for item in draft.diff_items)
    assert all(
        rejection.parsed_target_path is not None
        for rejection in draft.rejected_items
    )
    assert all(
        rejection.to_dict()["parsed_target_path"]["raw"] == rejection.target_path
        for rejection in draft.rejected_items
    )
    assert {
        rejection.reason
        for rejection in draft.rejected_items
    } == {"wildcard_path_not_resolved"}


def test_parse_tuning_config_path_splits_file_and_document_path():
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification"
    )

    assert parsed.raw == "config/signal_engine.yaml:signal_engine.classification"
    assert parsed.file_path == "config/signal_engine.yaml"
    assert parsed.document_path == "signal_engine.classification"
    assert parsed.to_dict() == {
        "raw": "config/signal_engine.yaml:signal_engine.classification",
        "file_path": "config/signal_engine.yaml",
        "document_path": "signal_engine.classification",
    }


def test_parse_tuning_config_path_rejects_invalid_format():
    invalid_paths = (
        "config/signal_engine.yaml",
        "config/signal_engine.yaml:",
        ":signal_engine.classification",
        "config/signal_engine.json:signal_engine.classification",
    )

    for invalid_path in invalid_paths:
        try:
            parse_tuning_config_path(invalid_path)
        except ValueError:
            continue
        raise AssertionError(f"Expected invalid path to fail: {invalid_path}")


def test_resolve_tuning_config_value_reads_concrete_yaml_path(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n",
        encoding="utf-8",
    )
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
    )

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is True
    assert resolution.current_value == 70
    assert resolution.unresolved_reason is None
    assert resolution.to_dict()["current_value"] == 70


def test_resolve_tuning_config_value_rejects_wildcard_without_reading_yaml(tmp_path):
    parsed = parse_tuning_config_path("config/swing_setups.yaml:setups.*.gates")

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is False
    assert resolution.current_value is None
    assert resolution.unresolved_reason == "wildcard_path_not_resolved"


def test_resolve_tuning_config_value_reports_missing_document_path(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification: {}\n",
        encoding="utf-8",
    )
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
    )

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is False
    assert resolution.current_value is None
    assert resolution.unresolved_reason == "document_path_not_found"


def test_validate_tuning_target_paths_covers_all_current_targets():
    summary = summarize_swing_backtest_attribution(())

    parsed_paths = validate_tuning_target_paths(summary)

    assert parsed_paths
    assert set(parsed_paths) == {
        yaml_path
        for target in summary.tuning_targets
        for yaml_path in target.yaml_paths
    }
