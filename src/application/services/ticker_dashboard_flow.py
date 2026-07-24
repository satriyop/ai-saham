"""
Foreign-flow selection helpers for the ticker dashboard.

Layer: Application
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.entities.broker_flow import ForeignFlowPoint

FOREIGN_FLOW_SOURCE_PREFERENCE = ("stockbit", "idx")
FOREIGN_FLOW_WINDOWS = (5, 20)


def select_foreign_flow_points(
    points_by_source: dict[str, list[ForeignFlowPoint]],
) -> tuple[list[ForeignFlowPoint], str | None]:
    """Pick the preferred non-empty foreign-flow series for the dashboard."""
    for source in FOREIGN_FLOW_SOURCE_PREFERENCE:
        points = points_by_source.get(source) or []
        if points:
            return points, source
    for source, points in points_by_source.items():
        if points:
            return points, source
    return [], None


def window_net(points: list[ForeignFlowPoint], days: int) -> Decimal | None:
    if not points or days <= 0:
        return None
    window = points[-days:]
    return sum((p.net_val for p in window), Decimal("0"))


def window_buy_sell_days(points: list[ForeignFlowPoint], days: int) -> tuple[int, int]:
    if not points or days <= 0:
        return 0, 0
    window = points[-days:]
    buy_days = sum(1 for p in window if p.net_val > 0)
    sell_days = len(window) - buy_days
    return buy_days, sell_days
