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
class SwingBacktestAttributionSummary:
    """Grouped deterministic evidence for tuning swing workflow YAML."""

    intent: str = (
        "learning_summary_only_not_entry_logic"
    )
    group_stats: tuple[AttributionGroupStat, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "group_stats": [stat.to_dict() for stat in self.group_stats],
        }


def summarize_swing_backtest_attribution(
    trades: Iterable[Any],
) -> SwingBacktestAttributionSummary:
    """Build deterministic grouped attribution from completed backtest trades."""
    rows = list(trades)
    groups: dict[tuple[str, str], list[Any]] = {}

    for trade in rows:
        for dimension, bucket in _trade_buckets(trade):
            groups.setdefault((dimension, bucket), []).append(trade)

    stats = tuple(
        sorted(
            (
                _build_stat(dimension, bucket, bucket_trades)
                for (dimension, bucket), bucket_trades in groups.items()
            ),
            key=lambda stat: (stat.dimension, -stat.trade_count, stat.bucket),
        )
    )
    return SwingBacktestAttributionSummary(group_stats=stats)


def _trade_buckets(trade: Any) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "trade_setup_action", getattr(trade, "trade_setup_action", None))
    _add(buckets, "risk_status", getattr(trade, "risk_status", None))
    _add(buckets, "risk_gate", getattr(trade, "risk_gate", None))
    _add(buckets, "signal_strength", getattr(trade, "signal_strength", None))
    _add(buckets, "signal_score_bucket", _score_bucket(getattr(trade, "signal_score", None)))
    _add(buckets, "regime", getattr(trade, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(trade, "setup_gates", ()))
    _add_signal_factor_buckets(buckets, getattr(trade, "signal_breakdown", ()))
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
) -> None:
    for name, value in signal_breakdown:
        buckets.append(("signal_factor_bucket", f"{name}:{_factor_bucket(value)}"))


def _score_bucket(value: int | float | None) -> str | None:
    if value is None:
        return None
    if value >= 70:
        return "HIGH_70_PLUS"
    if value >= 45:
        return "MID_45_69"
    return "LOW_BELOW_45"


def _factor_bucket(value: float) -> str:
    if value >= 70:
        return "HIGH_70_PLUS"
    if value >= 45:
        return "MID_45_69"
    return "LOW_BELOW_45"


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
