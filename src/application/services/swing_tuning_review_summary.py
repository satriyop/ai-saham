"""Raw-record summarization for swing tuning review artifacts.

Layer: Application
"""

from __future__ import annotations

from typing import Any

from src.application.dto.swing_tuning_review import (
    SwingTuningMetricDelta,
    SwingTuningReviewSummary,
)


def summarize_review_record(record: dict[str, Any]) -> SwingTuningReviewSummary:
    sample = _dict(record.get("sample"))
    backtest = _dict(record.get("backtest_summary"))
    tuning_diff = _dict(record.get("tuning_config_diff"))
    tuning_diff_summary = _dict(tuning_diff.get("summary"))
    is_ratio_raw = _float(record.get("is_ratio"))
    # walk_forward_enforced is True only when the backtest was actually run on the
    # IS window — signalled by is_end_date being present in the record. Storing
    # is_ratio alone does not constitute enforcement; it's metadata.
    walk_forward_enforced = _str(record.get("is_end_date")) is not None
    oos = _dict(record.get("oos_backtest_summary"))
    return SwingTuningReviewSummary(
        recorded_at=_str(record.get("recorded_at")),
        setup=_str(record.get("setup")),
        start_date=_str(record.get("start_date")),
        end_date=_str(record.get("end_date")),
        sample_status=_str(sample.get("status")),
        min_sample_size=_int(sample.get("min_sample_size")),
        trade_count=_int(backtest.get("trade_count")),
        candidate_observation_count=_int(
            backtest.get("candidate_observation_count")
        ),
        total_return_pct=_float(backtest.get("total_return_pct")),
        win_rate_pct=_float(backtest.get("win_rate_pct")),
        tuning_diff_status=_str(tuning_diff.get("status")),
        proposed_count=_int(tuning_diff_summary.get("proposed_count")),
        rejected_count=_int(tuning_diff_summary.get("rejected_count")),
        is_ratio=is_ratio_raw,
        walk_forward_enforced=walk_forward_enforced,
        oos_trade_count=_int(oos.get("trade_count")),
        oos_total_return_pct=_float(oos.get("total_return_pct")),
        oos_win_rate_pct=_float(oos.get("win_rate_pct")),
    )


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _str(value: object) -> str | None:
    return str(value) if value is not None else None


def _int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _metric_deltas(
    baseline: SwingTuningReviewSummary,
    candidate: SwingTuningReviewSummary,
) -> tuple[SwingTuningMetricDelta, ...]:
    specs = (
        ("trade_count", baseline.trade_count, candidate.trade_count),
        (
            "candidate_observation_count",
            baseline.candidate_observation_count,
            candidate.candidate_observation_count,
        ),
        ("total_return_pct", baseline.total_return_pct, candidate.total_return_pct),
        ("win_rate_pct", baseline.win_rate_pct, candidate.win_rate_pct),
        ("proposed_count", baseline.proposed_count, candidate.proposed_count),
        ("rejected_count", baseline.rejected_count, candidate.rejected_count),
        ("is_ratio", baseline.is_ratio, candidate.is_ratio),
        ("oos_trade_count", baseline.oos_trade_count, candidate.oos_trade_count),
        ("oos_total_return_pct", baseline.oos_total_return_pct, candidate.oos_total_return_pct),
        ("oos_win_rate_pct", baseline.oos_win_rate_pct, candidate.oos_win_rate_pct),
    )
    return tuple(
        SwingTuningMetricDelta(
            name=name,
            baseline_value=baseline_value,
            candidate_value=candidate_value,
            delta=_delta(baseline_value, candidate_value),
        )
        for name, baseline_value, candidate_value in specs
    )


def _delta(
    baseline_value: int | float | None,
    candidate_value: int | float | None,
) -> int | float | None:
    if baseline_value is None or candidate_value is None:
        return None
    return candidate_value - baseline_value
