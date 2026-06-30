"""Deterministic attribution summary for swing backtest tuning.

Intent:
    This module turns completed swing backtest trades into grouped evidence for
    human/AI-assisted YAML tuning. It is a reporting/learning artifact only.
    It must not be used by live entry logic, backtest entry filtering, or risk
    decisions.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from src.application.services.stats import average, profit_factor, win_rate


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
    group_stats: tuple[AttributionGroupStat, ...] = field(default_factory=tuple)
    candidate_group_stats: tuple[CandidateAttributionStat, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "bucket_policy": self.bucket_policy.to_dict(),
            "group_stats": [stat.to_dict() for stat in self.group_stats],
            "candidate_group_stats": [
                stat.to_dict() for stat in self.candidate_group_stats
            ],
        }


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
        for dimension, bucket in _trade_buckets(trade, policy):
            groups.setdefault((dimension, bucket), []).append(trade)

    for observation in observation_rows:
        for dimension, bucket in _candidate_buckets(observation, policy):
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
        group_stats=stats,
        candidate_group_stats=candidate_stats,
    )


def _trade_buckets(
    trade: Any,
    bucket_policy: AttributionBucketPolicy,
) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "trade_setup_action", getattr(trade, "trade_setup_action", None))
    _add(buckets, "risk_status", getattr(trade, "risk_status", None))
    _add(buckets, "risk_gate", getattr(trade, "risk_gate", None))
    _add(buckets, "signal_strength", getattr(trade, "signal_strength", None))
    _add(
        buckets,
        "signal_score_bucket",
        _score_bucket(getattr(trade, "signal_score", None), bucket_policy),
    )
    _add(buckets, "regime", getattr(trade, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(trade, "setup_gates", ()))
    _add_signal_factor_buckets(
        buckets,
        getattr(trade, "signal_breakdown", ()),
        bucket_policy,
    )
    return tuple(buckets)


def _candidate_buckets(
    observation: Any,
    bucket_policy: AttributionBucketPolicy,
) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "candidate_setup_match", getattr(observation, "setup_match", None))
    _add(buckets, "candidate_signal_strength", getattr(observation, "signal_strength", None))
    _add(
        buckets,
        "candidate_signal_score_bucket",
        _score_bucket(getattr(observation, "signal_score", None), bucket_policy),
    )
    _add(buckets, "candidate_risk_status", getattr(observation, "risk_status", None))
    _add(buckets, "candidate_risk_gate", getattr(observation, "risk_gate", None))
    _add(buckets, "candidate_trade_setup_action", getattr(observation, "trade_setup_action", None))
    _add(buckets, "candidate_regime", getattr(observation, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(observation, "setup_gates", ()))
    _add_signal_factor_buckets(
        buckets,
        getattr(observation, "signal_breakdown", ()),
        bucket_policy,
        dimension="candidate_signal_factor_bucket",
    )
    return tuple(buckets)


def _add(buckets: list[tuple[str, str]], dimension: str, bucket: object | None) -> None:
    if bucket is None:
        return
    bucket_text = str(bucket)
    if bucket_text:
        buckets.append((dimension, bucket_text))


def _add_setup_gate_buckets(
    buckets: list[tuple[str, str]],
    setup_gates: Iterable[Any],
) -> None:
    for gate in setup_gates:
        label = getattr(gate, "label", None)
        if not label:
            continue
        status = "PASS" if getattr(gate, "passed", False) else "FAIL"
        buckets.append(("setup_gate", f"{label}:{status}"))


def _add_signal_factor_buckets(
    buckets: list[tuple[str, str]],
    signal_breakdown: Iterable[tuple[str, float]],
    bucket_policy: AttributionBucketPolicy,
    dimension: str = "signal_factor_bucket",
) -> None:
    for name, value in signal_breakdown:
        buckets.append((
            dimension,
            f"{name}:{_score_bucket(value, bucket_policy)}",
        ))


def _score_bucket(
    value: int | float | None,
    bucket_policy: AttributionBucketPolicy,
) -> str | None:
    if value is None:
        return None
    high = _format_threshold(bucket_policy.high_min_score)
    mid = _format_threshold(bucket_policy.mid_min_score)
    high_floor = _format_threshold(bucket_policy.high_min_score - 1)
    if value >= bucket_policy.high_min_score:
        return f"HIGH_{high}_PLUS"
    if value >= bucket_policy.mid_min_score:
        return f"MID_{mid}_{high_floor}"
    return f"LOW_BELOW_{mid}"


def _format_threshold(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value).replace(".", "_")


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
