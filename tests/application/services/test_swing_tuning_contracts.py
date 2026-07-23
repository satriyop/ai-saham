"""Swing tuning facade tests.

These tests cover orchestration contracts: readiness, proposals, guarded diff
drafts, and apply-block behavior. Helper internals belong in the focused
config-path and diff-policy test modules.
"""

from dataclasses import replace

import pytest

from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
    summarize_swing_backtest_attribution,
)
from src.application.services.swing_tuning_contracts import (
    assert_tuning_config_diff_apply_block,
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
)
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
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

    draft = build_tuning_config_diff_draft(summary, document_loader=swing_tuning_document_loader())

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
    assert {
        rejection.value_selection_policy
        for rejection in draft.rejected_items
    } == {"INSUFFICIENT_EVIDENCE"}
    assert {
        rejection.to_dict()["value_selection_policy"]
        for rejection in draft.rejected_items
    } == {"INSUFFICIENT_EVIDENCE"}
    assert {
        rejection.to_dict()["interpretation"]
        for rejection in draft.rejected_items
    } == {"not resolved; readiness blocked"}
    summary = draft.to_dict()["summary"]
    assert summary["resolved_count"] == 0
    assert summary["proposed_count"] == 0
    assert summary["current_only_count"] == 0
    assert summary["rejected_count"] == len(DEFAULT_TUNING_TARGETS)
    assert (
        "Resolve rejected rows before expecting a complete tuning diff."
        in draft.to_dict()["review_checklist"]
    )
    assert draft.to_dict()["review_checklist"][-1] == (
        "Do not apply automatically; edit YAML manually only after review."
    )
    assert "dry-run" in " ".join(draft.notes)


def test_tuning_config_diff_draft_explains_non_value_selected_paths():
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

    draft = build_tuning_config_diff_draft(summary, document_loader=swing_tuning_document_loader())

    assert draft.status == "READ_ONLY_VALUES"
    assert draft.proposal_status == "READY_FOR_HUMAN_REVIEW"
    assert draft.can_apply is False
    assert draft.diff_items
    assert {
        item.status
        for item in draft.diff_items
    } == {"CURRENT_VALUE_ONLY"}
    assert {
        item.confidence
        for item in draft.diff_items
    } == {"READ_ONLY_CURRENT_VALUE"}
    assert {
        item.value_selection_policy
        for item in draft.diff_items
    } == {"INSUFFICIENT_EVIDENCE", "NON_NUMERIC_CURRENT_VALUE"}
    assert {
        item.to_dict()["value_selection_policy"]
        for item in draft.diff_items
    } == {"INSUFFICIENT_EVIDENCE", "NON_NUMERIC_CURRENT_VALUE"}
    assert {
        item.to_dict()["interpretation"]
        for item in draft.diff_items
    } == {
        "read-only current value; evidence below high",
        "read-only current value; non-numeric config",
    }
    assert all(
        item.to_dict()["evidence_snapshot"]["sample_count"] == 30
        for item in draft.diff_items
    )
    assert all(
        item.to_dict()["evidence_snapshot"]["evidence_strength"]
        for item in draft.diff_items
    )
    assert (
        "Inspect current-only rows before treating them as tunable."
        in draft.to_dict()["review_checklist"]
    )
    assert all(item.current_value is not None for item in draft.diff_items)
    assert all(item.proposed_value is None for item in draft.diff_items)
    assert all(item.parsed_target_path is not None for item in draft.diff_items)
    assert {
        item.target_path
        for item in draft.diff_items
        if item.target_path.startswith("config/swing_setups.yaml:setups.")
    }
    assert not draft.rejected_items


def test_tuning_config_diff_draft_selects_guarded_numeric_values(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n"
        "    moderate_min_score: 45\n",
        encoding="utf-8",
    )
    summary = summarize_swing_backtest_attribution(
        tuple(
            make_trade(
                ticker=f"T{i:03}",
                net_return_pct=-2.0 if i < 30 else 5.0,
                pnl="-200" if i < 30 else "500",
                signal_strength="STRONG" if i < 30 else "WEAK",
            )
            for i in range(60)
        )
    )

    draft = build_tuning_config_diff_draft(summary, document_loader=swing_tuning_document_loader(tmp_path))
    threshold_items = {
        item.parsed_target_path.document_path: item
        for item in draft.diff_items
        if item.parsed_target_path is not None
        and item.evidence_dimension == "signal_strength"
        and item.parsed_target_path.document_path.startswith(
            "signal_engine.classification."
        )
    }

    assert draft.status == "PROPOSED_VALUES_DRY_RUN"
    assert draft.can_apply is False
    assert draft.requires_human_review is True
    assert threshold_items[
        "signal_engine.classification.strong_min_score"
    ].current_value == 70
    assert threshold_items[
        "signal_engine.classification.strong_min_score"
    ].proposed_value == 71
    assert "signal_strength" in threshold_items[
        "signal_engine.classification.strong_min_score"
    ].evidence_dimensions
    assert len(
        threshold_items[
            "signal_engine.classification.strong_min_score"
        ].evidence_dimensions
    ) > 1
    assert threshold_items[
        "signal_engine.classification.moderate_min_score"
    ].current_value == 45
    assert threshold_items[
        "signal_engine.classification.moderate_min_score"
    ].proposed_value == 46
    assert {
        item.status for item in threshold_items.values()
    } == {"PROPOSED_VALUE_SELECTED"}
    assert {
        item.confidence for item in threshold_items.values()
    } == {"DETERMINISTIC_GUARDED"}
    assert {
        item.value_selection_policy for item in threshold_items.values()
    } == {"DETERMINISTIC_VALUE_SELECTED"}
    assert {
        item.to_dict()["interpretation"] for item in threshold_items.values()
    } == {"proposed guarded value"}
    assert {
        item.to_dict()["target_classification"]["target_family"]
        for item in threshold_items.values()
    } == {"signal_engine"}
    assert {
        item.to_dict()["target_classification"]["target_kind"]
        for item in threshold_items.values()
    } == {"classification"}
    assert threshold_items[
        "signal_engine.classification.strong_min_score"
    ].to_dict()["target_classification"]["target_parameter"] == (
        "strong_min_score"
    )
    assert {
        item.to_dict()["evidence_snapshot"]["sample_count"]
        for item in threshold_items.values()
    } == {60}
    assert {
        item.to_dict()["evidence_snapshot"]["evidence_strength"]
        for item in threshold_items.values()
    } == {"HIGH"}
    assert {
        item.to_dict()["evidence_snapshot"]["proposed_action"]
        for item in threshold_items.values()
    } == {"review_threshold_or_weight_no_yaml_diff"}
    assert all(
        item.to_dict()["evidence_snapshot"]["evidence_buckets"]
        for item in threshold_items.values()
    )
    assert (
        "Review every proposed value before editing YAML manually."
        in draft.to_dict()["review_checklist"]
    )
    summary_dict = draft.to_dict()["summary"]
    assert summary_dict["resolved_count"] == len(draft.diff_items)
    assert summary_dict["proposed_count"] >= len(threshold_items)
    assert summary_dict["current_only_count"] == (
        len(draft.diff_items) - summary_dict["proposed_count"]
    )
    assert summary_dict["rejected_count"] == len(draft.rejected_items)
    assert (
        summary_dict["value_policy_counts"]["DETERMINISTIC_VALUE_SELECTED"]
        >= len(threshold_items)
    )
    assert summary_dict["evidence_dimension_counts"]["signal_strength"] >= len(
        threshold_items
    )


def test_tuning_config_diff_draft_deduplicates_target_paths(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n"
        "    moderate_min_score: 45\n",
        encoding="utf-8",
    )
    summary = summarize_swing_backtest_attribution(
        tuple(
            make_trade(
                ticker=f"T{i:03}",
                net_return_pct=-2.0 if i < 30 else 5.0,
                pnl="-200" if i < 30 else "500",
                signal_strength="STRONG" if i < 30 else "WEAK",
            )
            for i in range(60)
        )
    )

    draft = build_tuning_config_diff_draft(summary, document_loader=swing_tuning_document_loader(tmp_path))
    target_paths = [item.target_path for item in draft.diff_items]
    strong_threshold = next(
        item
        for item in draft.diff_items
        if item.target_path
        == "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
    )

    assert len(target_paths) == len(set(target_paths))
    assert strong_threshold.evidence_dimension == "signal_strength"
    assert {
        "signal_strength",
        "signal_score_bucket",
        "trade_setup_action",
    } <= set(strong_threshold.evidence_dimensions)
    assert strong_threshold.to_dict()["evidence_dimensions"] == list(
        strong_threshold.evidence_dimensions
    )


def test_tuning_config_diff_draft_can_loosen_setup_thresholds(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "swing_setups.yaml").write_text(
        "setups:\n"
        "  foreign-bounce:\n"
        "    gates:\n"
        "      min_accum_score: 70\n"
        "      max_rsi: 60\n"
        "      required_trend: SIDE\n"
        "    partial_max_failed_gates: 2\n",
        encoding="utf-8",
    )
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(
            ObservationFixture(
                forward_return_pct=-2.0 if i < 30 else 5.0,
                setup_match="MATCH" if i < 30 else "NO_MATCH",
            )
            for i in range(60)
        ),
    )

    draft = build_tuning_config_diff_draft(summary, document_loader=swing_tuning_document_loader(tmp_path))
    by_path = {item.target_path: item for item in draft.diff_items}

    assert draft.status == "PROPOSED_VALUES_DRY_RUN"
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.gates.min_accum_score"
    ].proposed_value == 69
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.gates.max_rsi"
    ].proposed_value == 61
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.partial_max_failed_gates"
    ].proposed_value == 3
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.gates.required_trend"
    ].proposed_value is None
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.gates.min_accum_score"
    ].value_selection_policy == "DETERMINISTIC_VALUE_SELECTED"
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.gates.min_accum_score"
    ].to_dict()["target_classification"] == {
        "target_family": "swing_setup",
        "target_kind": "gate",
        "target_parameter": "min_accum_score",
    }
    assert by_path[
        "config/swing_setups.yaml:setups.foreign-bounce.partial_max_failed_gates"
    ].to_dict()["target_classification"] == {
        "target_family": "swing_setup",
        "target_kind": "threshold",
        "target_parameter": "partial_max_failed_gates",
    }


def test_tuning_config_diff_apply_block_rejects_applyable_drafts(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n"
        "    moderate_min_score: 45\n",
        encoding="utf-8",
    )
    summary = summarize_swing_backtest_attribution(
        tuple(
            make_trade(
                ticker=f"T{i:03}",
                net_return_pct=-2.0 if i < 30 else 5.0,
                pnl="-200" if i < 30 else "500",
                signal_strength="STRONG" if i < 30 else "WEAK",
            )
            for i in range(60)
        )
    )

    draft = build_tuning_config_diff_draft(summary, document_loader=swing_tuning_document_loader(tmp_path))

    assert draft.status == "PROPOSED_VALUES_DRY_RUN"
    assert assert_tuning_config_diff_apply_block(draft) is draft
    for unsafe_draft in (
        replace(draft, can_apply=True),
        replace(draft, requires_human_review=False),
        replace(draft, intent="config_diff_apply"),
    ):
        with pytest.raises(ValueError, match="apply block violated"):
            assert_tuning_config_diff_apply_block(unsafe_draft)


def test_tuning_targets_include_concrete_signal_risk_and_market_paths():
    summary = summarize_swing_backtest_attribution(())
    paths = {
        yaml_path
        for target in summary.tuning_targets
        for yaml_path in target.yaml_paths
    }

    assert {
        "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
        "config/signal_engine.yaml:signal_engine.evidence_groups.flow_confirmation.weight",
        "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr",
        "config/risk_engine.yaml:risk_engine.gates.free_float.min_free_float_pct",
        "config/market_context_engine.yaml:market_context_engine.regime_thresholds.risk_on_min_score",
        "config/swing_targets.yaml:setup_targets.risk_off.stop_loss_pct",
    } <= paths
