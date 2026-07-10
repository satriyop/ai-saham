"""Pure numeric and grouping math helpers for institutional accumulation."""

from __future__ import annotations

from datetime import date

from src.domain.entities.broker_flow import BrokerDailyFlow

_VWAP_NEAR = 0.02
_VWAP_FAR = 0.20


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _slope(values: list[float]) -> float:
    """Ordinary least-squares slope of ``values`` against index 0..n-1."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    return num / denom


def _group_by_date(
    flows: list[BrokerDailyFlow],
) -> dict[date, list[BrokerDailyFlow]]:
    grouped: dict[date, list[BrokerDailyFlow]] = {}
    for flow in flows:
        grouped.setdefault(flow.date, []).append(flow)
    return grouped


def _vwap_distance_score(current_price: float, vwap: float) -> float | None:
    """Saturating score: 1.0 within NEAR of VWAP, 0.0 once FAR above VWAP."""
    if vwap <= 0:
        return None
    distance = (current_price - vwap) / vwap
    if distance <= _VWAP_NEAR:
        return 1.0
    if distance >= _VWAP_FAR:
        return 0.0
    return _clamp01(1.0 - (distance - _VWAP_NEAR) / (_VWAP_FAR - _VWAP_NEAR))
