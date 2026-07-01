from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
    summarize_swing_backtest_attribution,
)
from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
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
    assert "schema-only" in " ".join(draft.notes)


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

    assert draft.status == "SCHEMA_ONLY"
    assert draft.proposal_status == "READY_FOR_HUMAN_REVIEW"
    assert draft.can_apply is False
    assert draft.diff_items == ()
    assert draft.rejected_items
    assert all(rejection.target_path != "N/A" for rejection in draft.rejected_items)
    assert {
        rejection.reason
        for rejection in draft.rejected_items
    } <= {
        "Config diff generation requires HIGH evidence strength; current strength is MEDIUM.",
        "Config diff generation requires HIGH evidence strength; current strength is LOW.",
        "Value-selection logic is not implemented; schema is locked first.",
    }
