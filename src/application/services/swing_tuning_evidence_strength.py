"""Attribution evidence extraction, strength, priority, and bucket formatting.

Intent:
    Deterministic helpers that classify attribution evidence quality for
    swing tuning proposals. No AI calls, no config mutation.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
    CandidateAttributionStat,
    SwingBacktestAttributionSummary,
)

__all__ = (
    "TuningDimensionEvidence",
    "build_tuning_evidence_by_dimension",
    "classify_tuning_evidence_strength",
    "calculate_tuning_evidence_priority",
    "format_tuning_evidence_bucket",
)


@dataclass(frozen=True)
class TuningDimensionEvidence:
    """Aggregated attribution evidence for a single tuning dimension."""

    buckets: tuple[str, ...]
    sample_count: int
    return_spread_pct: float | None
    strength: str
    priority: int


def build_tuning_evidence_by_dimension(
    summary: SwingBacktestAttributionSummary,
) -> dict[str, TuningDimensionEvidence]:
    evidence: dict[str, TuningDimensionEvidence] = {}
    stats = tuple(summary.group_stats) + tuple(summary.candidate_group_stats)
    dimensions = sorted({stat.dimension for stat in stats})
    for dimension in dimensions:
        dimension_stats = [stat for stat in stats if stat.dimension == dimension]
        top_stats = sorted(
            dimension_stats,
            key=lambda stat: (
                _stat_sample_count(stat),
                _stat_return(stat) or 0.0,
                stat.bucket,
            ),
            reverse=True,
        )[:3]
        sample_count = sum(_stat_sample_count(stat) for stat in dimension_stats)
        returns = tuple(
            value
            for value in (_stat_return(stat) for stat in dimension_stats)
            if value is not None
        )
        spread = round(max(returns) - min(returns), 4) if returns else None
        strength = classify_tuning_evidence_strength(
            sample_count=sample_count,
            bucket_count=len(dimension_stats),
            return_spread_pct=spread,
            min_sample_size=summary.sample_quality.min_sample_size,
        )
        evidence[dimension] = TuningDimensionEvidence(
            buckets=tuple(format_tuning_evidence_bucket(stat) for stat in top_stats),
            sample_count=sample_count,
            return_spread_pct=spread,
            strength=strength,
            priority=calculate_tuning_evidence_priority(
                sample_count=sample_count,
                return_spread_pct=spread,
                strength=strength,
            ),
        )
    return evidence


def classify_tuning_evidence_strength(
    *,
    sample_count: int,
    bucket_count: int,
    return_spread_pct: float | None,
    min_sample_size: int,
) -> str:
    spread = return_spread_pct or 0.0
    if sample_count >= min_sample_size * 2 and bucket_count >= 2 and spread >= 2.0:
        return "HIGH"
    if sample_count >= min_sample_size and (bucket_count >= 2 or spread >= 1.0):
        return "MEDIUM"
    if sample_count >= min_sample_size:
        return "LOW"
    return "INSUFFICIENT"


def calculate_tuning_evidence_priority(
    *,
    sample_count: int,
    return_spread_pct: float | None,
    strength: str,
) -> int:
    strength_bonus = {
        "HIGH": 300,
        "MEDIUM": 200,
        "LOW": 100,
        "INSUFFICIENT": 0,
    }[strength]
    spread_bonus = min(int((return_spread_pct or 0.0) * 10), 100)
    sample_bonus = min(sample_count, 100)
    return strength_bonus + spread_bonus + sample_bonus


def _stat_sample_count(stat: AttributionGroupStat | CandidateAttributionStat) -> int:
    return getattr(stat, "trade_count", getattr(stat, "observation_count", 0))


def _stat_return(stat: AttributionGroupStat | CandidateAttributionStat) -> float | None:
    return getattr(
        stat,
        "avg_return_pct",
        getattr(stat, "avg_forward_return_pct", None),
    )


def format_tuning_evidence_bucket(
    stat: AttributionGroupStat | CandidateAttributionStat,
) -> str:
    avg_return = _stat_return(stat)
    avg_text = "N/A" if avg_return is None else f"{avg_return:+.2f}%"
    return f"{stat.bucket} | n={_stat_sample_count(stat)} | avg={avg_text}"
