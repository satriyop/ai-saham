"""Sample size, readiness, and performance constraint tests for swing tuning."""

import json

from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
)
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
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
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
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


def test_swing_tuning_attribution_readiness_valid_groups(tmp_path):
    # Proves 1. A complete source review with all three canonical groups passes attribution readiness.
    review = {**_COMPLETE_SOURCE_REVIEW}
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is True, report.issues


def test_swing_tuning_attribution_missing_coverage_bucket(tmp_path):
    # Proves 2. Missing signal_authority_coverage_bucket fails with its exact missing-buckets issue.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        "market_regime": review["attribution"]["market_regime"],
        "setup_readiness_status": review["attribution"]["setup_readiness_status"],
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready: attribution.signal_authority_coverage_bucket must include buckets" in issue
        for issue in report.issues
    )


def test_swing_tuning_attribution_missing_setup_readiness(tmp_path):
    # Proves 3. Missing setup_readiness_status fails with its exact missing-buckets issue.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        "market_regime": review["attribution"]["market_regime"],
        "signal_authority_coverage_bucket": review["attribution"]["signal_authority_coverage_bucket"],
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready: attribution.setup_readiness_status must include buckets" in issue
        for issue in report.issues
    )


def test_swing_tuning_attribution_empty_bucket_fails_closed(tmp_path):
    # Proves 4. An empty canonical bucket list fails closed.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        "market_regime": {"buckets": []},
        "signal_authority_coverage_bucket": {"buckets": []},
        "setup_readiness_status": {"buckets": []},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready: attribution.signal_authority_coverage_bucket must include buckets" in issue
        for issue in report.issues
    )


def test_swing_tuning_attribution_legacy_coverage_rejected_explicitly(tmp_path):
    # Proves 5. Legacy coverage_bucket is rejected explicitly.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        **review["attribution"],
        "coverage_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready: attribution.coverage_bucket was removed by HIGH-2; use attribution.signal_authority_coverage_bucket" in issue
        for issue in report.issues
    )


def test_swing_tuning_attribution_legacy_conviction_rejected_explicitly(tmp_path):
    # Proves 6. Legacy conviction_bucket is rejected explicitly.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        **review["attribution"],
        "conviction_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any(
        "sample_not_ready: attribution.conviction_bucket was removed by HIGH-2; use attribution.setup_readiness_status" in issue
        for issue in report.issues
    )


def test_swing_tuning_attribution_both_canonical_and_legacy_rejected(tmp_path):
    # Proves 7. A payload containing both canonical and legacy keys is rejected.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        **review["attribution"],
        "coverage_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
        "conviction_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("attribution.coverage_bucket was removed" in i for i in report.issues)
    assert any("attribution.conviction_bucket was removed" in i for i in report.issues)


def test_swing_tuning_attribution_legacy_only_rejected(tmp_path):
    # Proves 8. Legacy-only attribution is not accepted as compatibility input.
    review = {**_COMPLETE_SOURCE_REVIEW}
    review["attribution"] = {
        "market_regime": review["attribution"]["market_regime"],
        "coverage_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
        "conviction_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
    }
    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is False
    assert any("attribution.coverage_bucket was removed" in i for i in report.issues)
    assert any("attribution.conviction_bucket was removed" in i for i in report.issues)
    assert any("attribution.signal_authority_coverage_bucket must include buckets" in i for i in report.issues)
    assert any("attribution.setup_readiness_status must include buckets" in i for i in report.issues)


def test_swing_tuning_attribution_market_regime_dependency_still_executes(tmp_path):
    # Proves 9. Existing market-regime dependency checks still execute against canonical attribution.
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


def test_swing_tuning_attribution_from_summarize_labels(tmp_path):
    # Proves 10. Positive tuning fixtures contain no legacy attribution keys.
    # At least one positive test must construct the same canonical attribution shape
    # emitted by SummarizeSignalForwardLabelsUseCase, rather than merely renaming arbitrary fixture keys.
    from src.application.use_case.summarize_signal_forward_labels_use_case import (
        SignalForwardLabelAttributionBucket,
        SummarizeSignalForwardLabelsResponse,
    )

    # Construct buckets exactly as SummarizeSignalForwardLabelsUseCase would emit
    summarize_response = SummarizeSignalForwardLabelsResponse(
        buckets=(
            SignalForwardLabelAttributionBucket(
                group="market_regime",
                key="RISK_ON",
                observation_count=15,
                success_count=8,
                failure_count=7,
                neutral_count=0,
                unavailable_count=0,
                average_close_return=0.1,
                average_max_forward_return=0.2,
                average_max_adverse_excursion=-0.05,
            ),
            SignalForwardLabelAttributionBucket(
                group="market_regime",
                key="NEUTRAL",
                observation_count=15,
                success_count=8,
                failure_count=7,
                neutral_count=0,
                unavailable_count=0,
                average_close_return=0.1,
                average_max_forward_return=0.2,
                average_max_adverse_excursion=-0.05,
            ),
            SignalForwardLabelAttributionBucket(
                group="signal_authority_coverage_bucket",
                key="HIGH",
                observation_count=30,
                success_count=16,
                failure_count=14,
                neutral_count=0,
                unavailable_count=0,
                average_close_return=0.1,
                average_max_forward_return=0.2,
                average_max_adverse_excursion=-0.05,
            ),
            SignalForwardLabelAttributionBucket(
                group="setup_readiness_status",
                key="READY",
                observation_count=30,
                success_count=16,
                failure_count=14,
                neutral_count=0,
                unavailable_count=0,
                average_close_return=0.1,
                average_max_forward_return=0.2,
                average_max_adverse_excursion=-0.05,
            ),
        )
    )

    # Convert to source_review attribution payload structure dynamically
    attribution = {}
    for bucket in summarize_response.buckets:
        if bucket.group not in attribution:
            attribution[bucket.group] = {"buckets": []}
        bucket_dict = bucket.to_dict()
        if bucket.group == "market_regime":
            bucket_dict["oos_trade_count"] = bucket.observation_count
            bucket_dict["oos_profit"] = 0.5  # positive profit
        attribution[bucket.group]["buckets"].append(bucket_dict)

    review = {
        **_COMPLETE_SOURCE_REVIEW,
        "attribution": attribution,
    }

    report = _patch_with_source_review(review, tmp_path)
    assert report.valid is True, report.issues
    assert all("sample_not_ready" not in issue for issue in report.issues)
