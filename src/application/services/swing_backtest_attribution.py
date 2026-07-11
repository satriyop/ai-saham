"""Deterministic attribution summary for swing backtest tuning.

Intent:
    This module turns completed swing backtest trades into grouped evidence for
    human/AI-assisted YAML tuning. It is a reporting/learning artifact only.
    It must not be used by live entry logic, backtest entry filtering, or risk
    decisions.

Layer: Application
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from src.application.dto.swing_backtest_attribution import (
    AttributionBucketPolicy,
    AttributionGroupStat,
    CandidateAttributionStat,
    SampleQuality,
    SwingBacktestAttributionSummary,
    TuningTarget,  # noqa: F401  # re-export
)
from src.application.services.stats import average, profit_factor, win_rate
from src.application.services.swing_backtest_attribution_buckets import (
    candidate_attribution_buckets,
    trade_attribution_buckets,
)
from src.application.services.swing_tuning_target_catalog import (
    DEFAULT_TUNING_TARGETS,  # noqa: F401  # re-export
)

MIN_TUNING_SAMPLE_SIZE = 30


def _build_sample_quality(
    completed_trade_count: int,
    candidate_observation_count: int,
    min_sample_size: int = MIN_TUNING_SAMPLE_SIZE,
) -> SampleQuality:
    trade_ready = completed_trade_count >= min_sample_size
    candidate_ready = candidate_observation_count >= min_sample_size

    notes: list[str] = []
    if completed_trade_count == 0 and candidate_observation_count == 0:
        status = "INSUFFICIENT_SAMPLE"
        notes.append("No completed trades or candidate observations are available.")
    elif trade_ready and candidate_ready:
        status = "MIXED_READY"
        notes.append("Completed-trade and screened-candidate samples meet the minimum.")
    elif trade_ready:
        status = "TRADE_READY"
        notes.append("Completed-trade sample meets the minimum.")
        notes.append("Candidate sample is below the minimum; setup/risk gate tuning is weaker.")
    elif candidate_ready:
        status = "CANDIDATE_ONLY"
        notes.append("Screened-candidate sample meets the minimum.")
        notes.append(
            "Completed-trade sample is below the minimum; "
            "portfolio outcome tuning is blocked."
        )
    else:
        status = "INSUFFICIENT_SAMPLE"
        notes.append("Samples are below the minimum required for tuning suggestions.")

    if completed_trade_count < min_sample_size:
        notes.append(
            f"Completed trades: {completed_trade_count}/{min_sample_size} minimum."
        )
    if candidate_observation_count < min_sample_size:
        notes.append(
            f"Candidate observations: {candidate_observation_count}/{min_sample_size} minimum."
        )

    return SampleQuality(
        status=status,
        completed_trade_count=completed_trade_count,
        candidate_observation_count=candidate_observation_count,
        min_sample_size=min_sample_size,
        trade_sample_ready=trade_ready,
        candidate_sample_ready=candidate_ready,
        notes=tuple(notes),
    )


def summarize_swing_backtest_attribution(
    trades: Iterable[Any],
    candidate_observations: Iterable[Any] = (),
    bucket_policy: AttributionBucketPolicy | None = None,
) -> SwingBacktestAttributionSummary:
    """Build deterministic grouped attribution from completed backtest trades."""
    rows = list(trades)
    groups: dict[tuple[str, str], list[Any]] = {}
    observation_rows = list(candidate_observations)
    candidate_groups: dict[tuple[str, str], list[Any]] = {}
    policy = bucket_policy or AttributionBucketPolicy()

    for trade in rows:
        for dimension, bucket in trade_attribution_buckets(trade, policy):
            groups.setdefault((dimension, bucket), []).append(trade)

    for observation in observation_rows:
        for dimension, bucket in candidate_attribution_buckets(observation, policy):
            candidate_groups.setdefault((dimension, bucket), []).append(observation)

    stats = tuple(
        sorted(
            (
                _build_stat(dimension, bucket, bucket_trades)
                for (dimension, bucket), bucket_trades in groups.items()
            ),
            key=lambda stat: (stat.dimension, -stat.trade_count, stat.bucket),
        )
    )
    candidate_stats = tuple(
        sorted(
            (
                _build_candidate_stat(dimension, bucket, bucket_observations)
                for (dimension, bucket), bucket_observations in candidate_groups.items()
            ),
            key=lambda stat: (stat.dimension, -stat.observation_count, stat.bucket),
        )
    )
    return SwingBacktestAttributionSummary(
        bucket_policy=policy,
        sample_quality=_build_sample_quality(
            completed_trade_count=len(rows),
            candidate_observation_count=len(observation_rows),
        ),
        group_stats=stats,
        candidate_group_stats=candidate_stats,
    )


def _build_stat(
    dimension: str,
    bucket: str,
    trades: list[Any],
) -> AttributionGroupStat:
    return AttributionGroupStat(
        dimension=dimension,
        bucket=bucket,
        trade_count=len(trades),
        win_rate_pct=win_rate((trade.net_return_pct for trade in trades), precision=2),
        avg_return_pct=average((trade.net_return_pct for trade in trades), precision=4),
        total_pnl=sum((trade.pnl for trade in trades), Decimal("0")),
        profit_factor=profit_factor((trade.pnl for trade in trades), precision=4),
    )


def _build_candidate_stat(
    dimension: str,
    bucket: str,
    observations: list[Any],
) -> CandidateAttributionStat:
    return CandidateAttributionStat(
        dimension=dimension,
        bucket=bucket,
        observation_count=len(observations),
        win_rate_pct=win_rate(
            (observation.forward_return_pct for observation in observations),
            precision=2,
        ),
        avg_forward_return_pct=average(
            (observation.forward_return_pct for observation in observations),
            precision=4,
        ),
    )
