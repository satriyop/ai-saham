"""Tests for Phase 8 Walk-Forward Calibration Guardrails."""

import json
import time

from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
)
from src.application.services.swing_tuning_diff_policy import (
    _classify_tuning_target_kind,
)
from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
    _bounds_for_document_path,
    _is_quantized,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
    _summarize_record,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)
from src.application.services.swing_tuning_config_paths import parse_tuning_config_path
from src.application.services.swing_backtest_attribution import SwingBacktestAttributionSummary
from src.application.services.swing_tuning_contracts import build_tuning_config_diff_draft


_SIGNAL_ENGINE_YAML = (
    "signal_engine:\n"
    "  classification:\n"
    "    strong_min_score: 70\n"
    "    moderate_min_score: 45\n"
    "    enter_min_confidence: 0.70\n"
    "    watch_min_confidence: 0.40\n"
    "  evidence_groups:\n"
    "    setup_quality:\n"
    "      weight: 0.60\n"
    "    flow_confirmation:\n"
    "      weight: 0.40\n"
)


_COMPLETE_SOURCE_REVIEW = {
    "walk_forward_enforced": True,
    "is_ratio": 0.70,
    "is_end_date": "2026-04-01",
    "oos_start_date": "2026-04-02",
    "full_end_date": "2026-07-01",
    "sample": {"status": "TRADE_READY", "min_sample_size": 30},
    "backtest_summary": {"trade_count": 35},
    "oos_backtest_summary": {
        "trade_count": 8,
        "total_return_pct": 3.2,
        "win_rate_pct": 50.0,
        "profit_factor": 1.5,
    },
}


def _write_config(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "signal_engine.yaml").write_text(
        _SIGNAL_ENGINE_YAML,
        encoding="utf-8",
    )


def _validate_single(tmp_path, document_leaf, current_value, proposed_value):
    """Validate a one-item patch against config/signal_engine.yaml.

    Includes walk_forward_enforced=True in source_review so provenance guardrail
    does not interfere with range/quantization/shift-cap item-level tests.
    """
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
        "patch_items": [
            {
                "target_path": f"config/signal_engine.yaml:{document_leaf}",
                "current_value": current_value,
                "proposed_value": proposed_value,
            },
        ],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    return report.item_results[0]


_WEIGHT_PATH = "signal_engine.evidence_groups.setup_quality.weight"
_STRONG_PATH = "signal_engine.classification.strong_min_score"


# --- 1. _bounds_for_document_path ------------------------------------------

def test_bounds_for_document_path_known_returns_bounds():
    bounds = _bounds_for_document_path(_WEIGHT_PATH)
    assert bounds == (0.05, 1.0, 0.05, 0.10)


def test_bounds_for_document_path_unknown_returns_none():
    assert _bounds_for_document_path("signal_engine.unknown.path") is None


# --- 2. _is_quantized -------------------------------------------------------

def test_is_quantized_true_for_grid_value():
    assert _is_quantized(0.60, 0.05) is True


def test_is_quantized_false_for_off_grid_value():
    assert _is_quantized(0.63, 0.05) is False


# --- 3-5. range enforcement -------------------------------------------------

def test_range_rejects_weight_above_max(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 1.5)
    assert result.valid is False
    assert any("out_of_range" in issue for issue in result.issues)


def test_range_rejects_weight_below_min(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.02)
    assert result.valid is False
    assert any("out_of_range" in issue for issue in result.issues)


def test_range_accepts_in_bounds_weight(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.60)
    assert result.valid is True
    assert result.issues == ()


# --- 6-7. quantization enforcement -----------------------------------------

def test_quantization_rejects_off_grid_weight(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.63)
    assert result.valid is False
    assert any("not_quantized" in issue for issue in result.issues)


def test_quantization_accepts_on_grid_weight(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.65)
    assert result.valid is True
    assert result.issues == ()


# --- 8-11. shift cap enforcement -------------------------------------------

def test_shift_cap_rejects_large_weight_change(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.80)
    assert result.valid is False
    assert any("exceeds_shift_cap" in issue for issue in result.issues)


def test_shift_cap_accepts_small_weight_change(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.65)
    assert result.valid is True
    assert result.issues == ()


def test_shift_cap_accepts_score_change_within_cap(tmp_path):
    result = _validate_single(tmp_path, _STRONG_PATH, 70, 74)
    assert result.valid is True
    assert result.issues == ()


def test_shift_cap_rejects_score_change_over_cap(tmp_path):
    result = _validate_single(tmp_path, _STRONG_PATH, 70, 76)
    assert result.valid is False
    assert any("exceeds_shift_cap" in issue for issue in result.issues)


# --- 12-14. IS/OOS tracking in review journal ------------------------------

def test_summary_without_is_ratio_is_not_walk_forward_enforced():
    summary = _summarize_record({})
    assert summary.is_ratio is None
    assert summary.walk_forward_enforced is False


def test_summary_with_split_is_walk_forward_enforced():
    # walk_forward_enforced requires is_end_date in the record — storing is_ratio
    # alone is metadata only; it does not prove the backtest ran on the IS window.
    summary = _summarize_record({"is_ratio": 0.70, "is_end_date": "2026-04-01"})
    assert summary.is_ratio == 0.70
    assert summary.walk_forward_enforced is True


def test_summary_with_is_ratio_but_no_is_end_date_is_not_enforced():
    # is_ratio stored without is_end_date means the adapter did not trim the window.
    summary = _summarize_record({"is_ratio": 0.70})
    assert summary.is_ratio == 0.70
    assert summary.walk_forward_enforced is False


def test_compare_latest_notes_when_walk_forward_not_enforced(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    store = SwingTuningReviewJsonlWriter(path)
    store.append({
        "recorded_at": "2026-07-01T10:00:00+07:00",
        "artifact_type": "swing_tuning_review",
        "setup": "foreign-bounce",
        "is_ratio": 0.70,
        "backtest_summary": {"trade_count": 10},
    })
    store.append({
        "recorded_at": "2026-07-02T10:00:00+07:00",
        "artifact_type": "swing_tuning_review",
        "setup": "foreign-bounce",
        "is_ratio": 1.0,
        "backtest_summary": {"trade_count": 12},
    })

    comparison = SwingTuningReviewJournal(store).compare_latest()

    assert comparison.status == "READY"
    assert comparison.candidate.is_ratio == 1.0
    assert comparison.candidate.walk_forward_enforced is False
    assert any(
        note.startswith("walk_forward_not_enforced") for note in comparison.notes
    )


# --- 15-16. attribution allowlist extensions -------------------------------

def _target_by_dimension(dimension):
    return next(
        target for target in DEFAULT_TUNING_TARGETS if target.dimension == dimension
    )


def test_regime_target_includes_regime_conditioning_path():
    regime = _target_by_dimension("regime")
    assert (
        "config/signal_engine.yaml:"
        "signal_engine.regime_conditioning.neutral.weak_flow_discount"
        in regime.yaml_paths
    )


def test_signal_strength_target_includes_enter_min_confidence_path():
    signal_strength = _target_by_dimension("signal_strength")
    assert (
        "config/signal_engine.yaml:signal_engine.classification.enter_min_confidence"
        in signal_strength.yaml_paths
    )


# --- 17. patch provenance guardrail (walk_forward_not_enforced = hard issue) -

def test_patch_without_source_review_fails_validation(tmp_path):
    # Patches with no source_review (legacy or bypassed format) must fail: there
    # is no provenance guarantee that proposals came from IS data only.
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_patch_with_walk_forward_false_fails_validation(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": {"walk_forward_enforced": False},
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_patch_with_walk_forward_true_but_missing_oos_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": {
            "walk_forward_enforced": True,
            "is_ratio": 0.70,
            "is_end_date": "2026-04-01",
            "oos_start_date": "2026-04-02",
            "full_end_date": "2026-07-01",
            # oos_backtest_summary intentionally absent
        },
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_patch_with_complete_source_review_passes_validation(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is True
    assert all("walk_forward_not_enforced" not in issue for issue in report.issues)


def test_patch_oos_with_zero_trades_fails_sample_guard(tmp_path):
    # Walk-forward provenance is structurally valid with 0 OOS trades, but the
    # sample readiness guard now rejects it: oos_trade_count=0 < 5 minimum.
    # A patch must have at least 5 OOS trades to be applicable.
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": {
            **_COMPLETE_SOURCE_REVIEW,
            "oos_backtest_summary": {
                "trade_count": 0,
                "total_return_pct": None,
                "win_rate_pct": None,
            },
        },
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert all("walk_forward_not_enforced" not in issue for issue in report.issues)
    assert any("sample_not_ready" in issue and "OOS trade_count=0" in issue
               for issue in report.issues)


# --- 18b. walk_forward_enforced exact boolean + date ordering ----------------

def test_truthy_string_walk_forward_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": {
            **_COMPLETE_SOURCE_REVIEW,
            "walk_forward_enforced": "true",  # truthy but not bool True
        },
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_malformed_oos_start_date_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": {
            **_COMPLETE_SOURCE_REVIEW,
            "oos_start_date": "not-a-date",
        },
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_oos_start_date_not_after_is_end_date_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": {
            **_COMPLETE_SOURCE_REVIEW,
            "oos_start_date": "2026-04-01",  # same day as is_end_date, not after
        },
        "patch_items": [],
    }))
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


# --- 18. target_kind for evidence_groups.*.weight ----------------------------

def test_evidence_group_weight_classified_as_weight_kind():
    path = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.evidence_groups.setup_quality.weight"
    )
    assert _classify_tuning_target_kind(path) == "weight"


# --- 18. OOS backtest metrics stored in journal ------------------------------

def test_oos_backtest_summary_populated_from_record():
    record = {
        "is_ratio": 0.70,
        "is_end_date": "2026-04-01",
        "oos_backtest_summary": {
            "trade_count": 8,
            "total_return_pct": 4.2,
            "win_rate_pct": 50.0,
        },
    }
    summary = _summarize_record(record)
    assert summary.oos_trade_count == 8
    assert summary.oos_total_return_pct == 4.2
    assert summary.oos_win_rate_pct == 50.0


def test_oos_fields_none_when_no_oos_summary():
    summary = _summarize_record({"is_ratio": 1.0})
    assert summary.oos_trade_count is None
    assert summary.oos_total_return_pct is None
    assert summary.oos_win_rate_pct is None


# --- 19. performance budget: diff generation and patch validation -----------

def test_patch_diff_generation_within_performance_budget(tmp_path):
    # Pure-Python patch validation must complete within 1s on a single-item patch.
    # This is the per-item validation floor; a full sweep of N paths scales linearly.
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
        "patch_items": [
            {
                "target_path": "config/signal_engine.yaml:" + _WEIGHT_PATH,
                "current_value": 0.60,
                "proposed_value": 0.65,
            },
        ],
    }))
    start = time.monotonic()
    SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"Patch validation took {elapsed:.3f}s — exceeds 1s budget"


def test_tuning_config_diff_draft_within_performance_budget():
    # Profile build_tuning_config_diff_draft with populated attribution stats —
    # closer to the real calibration sweep than an empty summary.
    # Budget: 0.5s. A real 200-ticker / 12-month run must stay under 5s total;
    # the per-call floor dominates, so this test catches regressions early.
    from decimal import Decimal
    from src.application.services.swing_backtest_attribution import (
        AttributionGroupStat, CandidateAttributionStat, SampleQuality,
    )
    group_stats = tuple(
        AttributionGroupStat(
            dimension=f"dim_{i}",
            bucket=f"bucket_{j}",
            trade_count=10 + i + j,
            win_rate_pct=55.0,
            avg_return_pct=1.2,
            total_pnl=Decimal("500"),
            profit_factor=1.4,
        )
        for i in range(5)
        for j in range(4)
    )
    candidate_stats = tuple(
        CandidateAttributionStat(
            dimension=f"cdim_{i}",
            bucket=f"cbucket_{j}",
            observation_count=20,
            win_rate_pct=48.0,
            avg_forward_return_pct=0.8,
        )
        for i in range(5)
        for j in range(4)
    )
    summary = SwingBacktestAttributionSummary(
        sample_quality=SampleQuality(
            status="READY",
            completed_trade_count=200,
            candidate_observation_count=400,
            min_sample_size=30,
            trade_sample_ready=True,
            candidate_sample_ready=True,
            notes=(),
        ),
        group_stats=group_stats,
        candidate_group_stats=candidate_stats,
    )
    start = time.monotonic()
    build_tuning_config_diff_draft(summary)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"build_tuning_config_diff_draft took {elapsed:.3f}s — exceeds 0.5s budget"


# --- sample readiness guards --------------------------------------------------


def _patch_with_source_review(source_review: dict, tmp_path) -> object:
    _write_config(tmp_path)
    p = tmp_path / "patch.json"
    p.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": source_review,
        "patch_items": [],
    }))
    return SwingTuningPatchValidator(config_root=tmp_path).validate(p)


def test_trade_ready_source_review_passes_sample_guard(tmp_path):
    report = _patch_with_source_review(_COMPLETE_SOURCE_REVIEW, tmp_path)
    assert report.valid is True
    assert all("sample_not_ready" not in issue for issue in report.issues)


def test_candidate_only_status_fails_sample_guard(tmp_path):
    review = {**_COMPLETE_SOURCE_REVIEW, "sample": {"status": "CANDIDATE_ONLY"}}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue for issue in report.issues)
    assert any("TRADE_READY" in issue for issue in report.issues)


def test_is_trade_count_below_30_fails_sample_guard(tmp_path):
    review = {**_COMPLETE_SOURCE_REVIEW, "backtest_summary": {"trade_count": 16}}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue and "IS completed_trade_count=16" in issue
               for issue in report.issues)


def test_oos_trade_count_below_5_fails_sample_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {"trade_count": 2, "total_return_pct": 3.0, "win_rate_pct": 50.0},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue and "OOS trade_count=2" in issue
               for issue in report.issues)


def test_oos_return_too_negative_fails_sample_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {"trade_count": 8, "total_return_pct": -20.0, "win_rate_pct": 50.0},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue and "total_return_pct" in issue
               for issue in report.issues)


def test_oos_win_rate_below_floor_fails_sample_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {"trade_count": 8, "total_return_pct": 1.0, "win_rate_pct": 35.0},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue and "win_rate_pct" in issue
               for issue in report.issues)


# --- Finding 1: missing IS sample fields are now required ---

def test_missing_sample_dict_fails_guard(tmp_path):
    review = {k: v for k, v in _COMPLETE_SOURCE_REVIEW.items() if k != "sample"}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "source_review.sample" in i for i in report.issues)


def test_missing_backtest_summary_fails_guard(tmp_path):
    review = {k: v for k, v in _COMPLETE_SOURCE_REVIEW.items() if k != "backtest_summary"}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "backtest_summary" in i for i in report.issues)


def test_non_integer_is_trade_count_fails_guard(tmp_path):
    review = {**_COMPLETE_SOURCE_REVIEW, "backtest_summary": {"trade_count": "many"}}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "trade_count" in i for i in report.issues)


# --- Finding 3: profit_factor required and floor-checked ---

def test_missing_profit_factor_with_oos_trades_fails_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {"trade_count": 8, "total_return_pct": 2.0, "win_rate_pct": 55.0},
        # profit_factor key absent
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "profit_factor" in i for i in report.issues)


def test_null_profit_factor_with_oos_trades_fails_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            "trade_count": 8, "total_return_pct": 2.0,
            "win_rate_pct": 55.0, "profit_factor": None,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "profit_factor" in i for i in report.issues)


def test_profit_factor_below_floor_fails_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            "trade_count": 8, "total_return_pct": 2.0,
            "win_rate_pct": 55.0, "profit_factor": 0.75,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "profit_factor=0.75" in i for i in report.issues)


def test_profit_factor_exactly_at_floor_passes_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            "trade_count": 8, "total_return_pct": 2.0,
            "win_rate_pct": 55.0, "profit_factor": 1.0,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is True
    assert all("profit_factor" not in i for i in report.issues)


def test_null_oos_metrics_with_sufficient_oos_trades_fail_guard(tmp_path):
    # When OOS has 6 trades (>= 5 minimum), all metrics must be numeric.
    # Null return/win_rate/profit_factor are rejected — you cannot approve a patch
    # based on trades with no measurable outcome.
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {"trade_count": 6, "total_return_pct": None, "win_rate_pct": None},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue and "total_return_pct" in issue
               for issue in report.issues)
    assert any("sample_not_ready" in issue and "win_rate_pct" in issue
               for issue in report.issues)
    assert any("sample_not_ready" in issue and "profit_factor" in issue
               for issue in report.issues)
