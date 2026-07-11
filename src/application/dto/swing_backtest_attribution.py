from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _default_tuning_targets() -> tuple:
    from src.application.services.swing_tuning_target_catalog import (
        DEFAULT_TUNING_TARGETS,
    )

    return DEFAULT_TUNING_TARGETS


def _default_sample_quality() -> Any:
    from src.application.services.swing_backtest_attribution import (
        _build_sample_quality,
    )

    return _build_sample_quality(0, 0)


@dataclass(frozen=True)
class AttributionGroupStat:
    """Performance stats for one tuning dimension bucket."""

    dimension: str
    bucket: str
    trade_count: int
    win_rate_pct: float | None
    avg_return_pct: float | None
    total_pnl: Decimal
    profit_factor: float | None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "bucket": self.bucket,
            "trade_count": self.trade_count,
            "win_rate_pct": self.win_rate_pct,
            "avg_return_pct": self.avg_return_pct,
            "total_pnl": str(self.total_pnl),
            "profit_factor": self.profit_factor,
        }


@dataclass(frozen=True)
class SampleQuality:
    """Deterministic readiness gate for attribution-driven tuning."""

    status: str
    completed_trade_count: int
    candidate_observation_count: int
    min_sample_size: int
    trade_sample_ready: bool
    candidate_sample_ready: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "completed_trade_count": self.completed_trade_count,
            "candidate_observation_count": self.candidate_observation_count,
            "min_sample_size": self.min_sample_size,
            "trade_sample_ready": self.trade_sample_ready,
            "candidate_sample_ready": self.candidate_sample_ready,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CandidateAttributionStat:
    """Forward-return stats for screened candidates, including rejected setups."""

    dimension: str
    bucket: str
    observation_count: int
    win_rate_pct: float | None
    avg_forward_return_pct: float | None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "bucket": self.bucket,
            "observation_count": self.observation_count,
            "win_rate_pct": self.win_rate_pct,
            "avg_forward_return_pct": self.avg_forward_return_pct,
        }


@dataclass(frozen=True)
class TuningTarget:
    """Allowlisted config target for one attribution dimension."""

    dimension: str
    source_scope: str
    source_field: str
    meaning: str
    config_family: str
    yaml_paths: tuple[str, ...]
    allowed_use: str
    warning: str | None = None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "source_scope": self.source_scope,
            "source_field": self.source_field,
            "meaning": self.meaning,
            "config_family": self.config_family,
            "yaml_paths": list(self.yaml_paths),
            "allowed_use": self.allowed_use,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class AttributionBucketPolicy:
    """Score bucket boundaries for attribution grouping only."""

    high_min_score: float = 70.0
    mid_min_score: float = 45.0

    def __post_init__(self) -> None:
        if self.high_min_score <= self.mid_min_score:
            raise ValueError("high_min_score must be greater than mid_min_score")

    def to_dict(self) -> dict:
        return {
            "high_min_score": self.high_min_score,
            "mid_min_score": self.mid_min_score,
        }


@dataclass(frozen=True)
class SwingBacktestAttributionSummary:
    """Grouped deterministic evidence for tuning swing workflow YAML."""

    intent: str = "learning_summary_only_not_entry_logic"
    bucket_policy: AttributionBucketPolicy = field(default_factory=AttributionBucketPolicy)
    sample_quality: SampleQuality = field(default_factory=_default_sample_quality)
    group_stats: tuple[AttributionGroupStat, ...] = field(default_factory=tuple)
    candidate_group_stats: tuple[CandidateAttributionStat, ...] = field(default_factory=tuple)
    tuning_targets: tuple[TuningTarget, ...] = field(default_factory=_default_tuning_targets)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "bucket_policy": self.bucket_policy.to_dict(),
            "sample_quality": self.sample_quality.to_dict(),
            "group_stats": [stat.to_dict() for stat in self.group_stats],
            "candidate_group_stats": [
                stat.to_dict() for stat in self.candidate_group_stats
            ],
            "tuning_targets": [target.to_dict() for target in self.tuning_targets],
        }
