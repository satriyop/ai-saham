"""Sample size, readiness, and performance constraint tests for swing tuning."""

import json

from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
)
from tests.application.services.swing_tuning_guardrail_fixtures import (
    _COMPLETE_SOURCE_REVIEW,
    _patch_with_source_review,
    _write_config,
)


def test_patch_oos_with_zero_trades_fails_sample_guard(tmp_path):
    # Walk-forward provenance is structurally valid with 0 OOS trades, but the
    # sample readiness guard now rejects it: oos_trade_count=0 < 5 minimum.
    # A patch must have at least 5 OOS trades to be applicable.
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
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
            }
        )
    )
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert all("walk_forward_not_enforced" not in issue for issue in report.issues)
    assert any(
        "sample_not_ready" in issue and "OOS trade_count=0" in issue for issue in report.issues
    )


def test_trade_ready_source_review_passes_sample_guard(tmp_path):
    report = _patch_with_source_review(_COMPLETE_SOURCE_REVIEW, tmp_path)
    assert report.valid is True
    assert all("sample_not_ready" not in issue for issue in report.issues)


def test_mixed_ready_status_passes_sample_guard(tmp_path):
    # MIXED_READY = IS trades >= 30 AND candidate observations >= 30 — the
    # better state than TRADE_READY. Validator must accept it.
    review = {**_COMPLETE_SOURCE_REVIEW, "sample": {"status": "MIXED_READY"}}
    report = _patch_with_source_review(review, tmp_path)
    assert all("sample_not_ready" not in issue for issue in report.issues)


def test_candidate_only_status_fails_sample_guard(tmp_path):
    review = {**_COMPLETE_SOURCE_REVIEW, "sample": {"status": "CANDIDATE_ONLY"}}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue for issue in report.issues)
    assert any("TRADE_READY" in issue or "MIXED_READY" in issue for issue in report.issues)


def test_is_trade_count_below_30_fails_sample_guard(tmp_path):
    review = {**_COMPLETE_SOURCE_REVIEW, "backtest_summary": {"trade_count": 16}}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready" in issue and "IS completed_trade_count=16" in issue
        for issue in report.issues
    )


def test_oos_trade_count_below_5_fails_sample_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {"trade_count": 2, "total_return_pct": 3.0, "win_rate_pct": 50.0},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready" in issue and "OOS trade_count=2" in issue for issue in report.issues
    )


def test_diagnostic_ready_source_review_is_report_only_not_patchable(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "readiness_state": "DIAGNOSTIC_READY",
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "trade_count": 12,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("Diagnostic-ready output is report-only" in issue for issue in report.issues)


def test_missing_attribution_fails_phase_i_patch_guard(tmp_path):
    review = {k: v for k, v in _COMPLETE_SOURCE_REVIEW.items() if k != "attribution"}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("source_review.attribution" in issue for issue in report.issues)


def test_single_regime_dependency_fails_phase_i_patch_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "attribution": {
            **_COMPLETE_SOURCE_REVIEW["attribution"],
            "market_regime": {
                "buckets": [
                    {"key": "RISK_ON", "oos_trade_count": 28, "oos_profit": 1.0},
                    {"key": "NEUTRAL", "oos_trade_count": 2, "oos_profit": 0.1},
                ],
            },
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("single-regime" in issue for issue in report.issues)
    assert any("positive OOS regime count=1" in issue for issue in report.issues)


def test_oos_average_return_negative_fails_sample_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "average_return_pct": -0.1,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready" in issue and "average_return_pct" in issue for issue in report.issues
    )


def test_oos_drawdown_regression_fails_sample_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "drawdown_regression_pct": 0.1,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready" in issue and "drawdown_regression_pct" in issue
        for issue in report.issues
    )


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


def test_missing_profit_factor_with_oos_trades_fails_guard(tmp_path):
    oos = dict(_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"])
    oos.pop("profit_factor")
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": oos,
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "profit_factor" in i for i in report.issues)


def test_null_profit_factor_with_oos_trades_fails_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "profit_factor": None,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "profit_factor" in i for i in report.issues)


def test_profit_factor_below_floor_fails_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "profit_factor": 0.75,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in i and "profit_factor=0.75" in i for i in report.issues)


def test_profit_factor_exactly_at_phase_i_floor_passes_guard(tmp_path):
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "profit_factor": 1.15,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is True
    assert all("profit_factor" not in i for i in report.issues)


def test_null_oos_metrics_with_sufficient_oos_trades_fail_guard(tmp_path):
    # Patch-eligible OOS samples must include the canonical measurable outcomes.
    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "oos_backtest_summary": {
            **_COMPLETE_SOURCE_REVIEW["oos_backtest_summary"],
            "average_return_pct": None,
            "profit_factor": None,
            "drawdown_regression_pct": None,
        },
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("sample_not_ready" in issue and "profit_factor" in issue for issue in report.issues)
    assert any(
        "sample_not_ready" in issue and "average_return_pct" in issue for issue in report.issues
    )
    assert any(
        "sample_not_ready" in issue and "drawdown_regression_pct" in issue
        for issue in report.issues
    )
