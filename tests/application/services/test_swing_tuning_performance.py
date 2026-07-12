"""Performance budget, diff draft, and journal tracking tests for swing tuning."""

import json
import time
from decimal import Decimal

from src.application.services.swing_backtest_attribution import (
    SwingBacktestAttributionSummary,
)
from src.application.services.swing_tuning_config_paths import (
    parse_tuning_config_path,
)
from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
)
from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
)
from src.application.services.swing_tuning_review_journal import (
    _summarize_record,
)
from src.application.services.swing_tuning_target_classification import (
    TuningTargetClassification,
)
from tests.application.services.swing_tuning_guardrail_fixtures import (
    _COMPLETE_SOURCE_REVIEW,
    _WEIGHT_PATH,
    _write_config,
)


def test_evidence_group_weight_classified_as_weight_kind():
    path = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.evidence_groups.setup_quality.weight"
    )
    classification = TuningTargetClassification.from_path(path)
    assert classification.target_kind == "weight"


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


def test_patch_diff_generation_within_performance_budget(tmp_path):
    # Pure-Python patch validation must complete within 1s on a single-item patch.
    # This is the per-item validation floor; a full sweep of N paths scales linearly.
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
                        "target_path": "config/signal_engine.yaml:" + _WEIGHT_PATH,
                        "current_value": 0.60,
                        "proposed_value": 0.65,
                    },
                ],
            }
        )
    )
    start = time.monotonic()
    SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"Patch validation took {elapsed:.3f}s — exceeds 1s budget"


def test_tuning_config_diff_draft_within_performance_budget():
    # Profile build_tuning_config_diff_draft with populated attribution stats —
    # closer to the real calibration sweep than an empty summary.
    # Budget: 0.5s. A real 200-ticker / 12-month run must stay under 5s total;
    # the per-call floor dominates, so this test catches regressions early.
    from src.application.services.swing_backtest_attribution import (
        AttributionGroupStat,
        CandidateAttributionStat,
        SampleQuality,
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
    assert elapsed < 0.5, (
        f"build_tuning_config_diff_draft took {elapsed:.3f}s — exceeds 0.5s budget"
    )
