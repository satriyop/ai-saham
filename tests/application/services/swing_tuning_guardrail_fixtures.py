"""Shared fixtures and builders for swing tuning guardrail tests."""

import json

from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
)
from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
)
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)

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
    "readiness_state": "PATCH_ELIGIBLE",
    "walk_forward_enforced": True,
    "is_ratio": 0.70,
    "is_end_date": "2026-04-01",
    "oos_start_date": "2026-04-02",
    "full_end_date": "2026-07-01",
    "sample": {"status": "TRADE_READY", "min_sample_size": 30},
    "backtest_summary": {"trade_count": 60},
    "oos_backtest_summary": {
        "trade_count": 30,
        "total_return_pct": 3.2,
        "average_return_pct": 0.2,
        "win_rate_pct": 50.0,
        "profit_factor": 1.5,
        "drawdown_regression_pct": 0.0,
    },
    "attribution": {
        "market_regime": {
            "buckets": [
                {"key": "RISK_ON", "oos_trade_count": 15, "oos_profit": 1.0},
                {"key": "NEUTRAL", "oos_trade_count": 15, "oos_profit": 0.8},
            ],
        },
        "coverage_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
        "conviction_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
    },
}

_WEIGHT_PATH = "signal_engine.evidence_groups.setup_quality.weight"
_STRONG_PATH = "signal_engine.classification.strong_min_score"


def _target_by_dimension(dimension):
    return next(target for target in DEFAULT_TUNING_TARGETS if target.dimension == dimension)


def _write_config(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "signal_engine.yaml").write_text(
        _SIGNAL_ENGINE_YAML,
        encoding="utf-8",
    )


def _validate_single(tmp_path, document_leaf, current_value, proposed_value):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
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
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    return report.item_results[0]


def _patch_with_source_review(source_review: dict, tmp_path) -> object:
    _write_config(tmp_path)
    p = tmp_path / "patch.json"
    p.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": source_review,
                "patch_items": [],
            }
        )
    )
    return SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(p)
