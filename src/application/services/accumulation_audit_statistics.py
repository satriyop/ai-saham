"""
Grouped performance statistics for accumulation-audit replay records.

Layer: Application
AI usage: None
"""

from typing import Callable

from src.application.dto.accumulation_audit import (
    AccumulationAuditPolicy,
    AuditGroupStat,
    AuditRecord,
)
from src.application.services.stats import average, win_rate


class AccumulationAuditStatisticsBuilder:
    """Build grouped performance statistics across configured dimensions."""

    def build(
        self,
        records: list[AuditRecord],
        policy: AccumulationAuditPolicy,
    ) -> list[AuditGroupStat]:
        dimensions: dict[str, Callable[[AuditRecord], str]] = {
            "accum_score": lambda r: _range_bucket(
                r.accum_score,
                policy.buckets.accum_score,
            ),
            "streak": lambda r: _range_bucket(float(r.streak), policy.buckets.streak),
            "flow_pct": lambda r: _nullable_range_bucket(r.flow_pct, policy.buckets.flow_pct),
            "vwap_disc_pct": lambda r: _nullable_range_bucket(
                r.vwap_disc_pct, policy.buckets.vwap_disc_pct
            ),
            "rsi": lambda r: _nullable_range_bucket(r.rsi, policy.buckets.rsi),
            "bb_pctile": lambda r: _nullable_range_bucket(r.bb_pctile, policy.buckets.bb_pctile),
            "trend": lambda r: r.trend,
            "broker_quality": lambda r: r.broker_quality,
        }

        stats: list[AuditGroupStat] = []
        for dimension in policy.group_dimensions:
            bucket_fn = dimensions.get(dimension)
            if bucket_fn is None:
                continue
            buckets: dict[str, list[AuditRecord]] = {}
            for record in records:
                buckets.setdefault(bucket_fn(record), []).append(record)

            for bucket, rows in sorted(buckets.items()):
                stats.append(_make_group_stat(dimension, bucket, rows))

        return stats


def _avg(values: list[float | None]) -> float | None:
    return average(values, precision=4)


def _win_rate(values: list[float | None]) -> float | None:
    return win_rate(values, precision=2)


def _make_group_stat(
    dimension: str,
    bucket: str,
    records: list[AuditRecord],
) -> AuditGroupStat:
    return AuditGroupStat(
        dimension=dimension,
        bucket=bucket,
        count=len(records),
        avg_return_5d_pct=_avg([r.return_5d_pct for r in records]),
        avg_return_10d_pct=_avg([r.return_10d_pct for r in records]),
        avg_return_20d_pct=_avg([r.return_20d_pct for r in records]),
        win_rate_10d_pct=_win_rate([r.return_10d_pct for r in records]),
        avg_max_upside_pct=_avg([r.max_upside_pct for r in records]),
        avg_max_drawdown_pct=_avg([r.max_drawdown_pct for r in records]),
    )


def _fmt_edge(value: float | int) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _range_bucket(value: float, edges: tuple[float | int, ...]) -> str:
    ordered = tuple(sorted(edges))
    if not ordered:
        return "all"
    if value < float(ordered[0]):
        return f"<{_fmt_edge(ordered[0])}"
    for lower, upper in zip(ordered, ordered[1:]):
        if value < float(upper):
            return f"{_fmt_edge(lower)}-{_fmt_edge(upper)}"
    return f"{_fmt_edge(ordered[-1])}+"


def _nullable_range_bucket(
    value: float | None,
    edges: tuple[float | int, ...],
) -> str:
    if value is None:
        return "missing"
    return _range_bucket(value, edges)
