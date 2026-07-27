"""Unit tests for foreign-flow helpers on the ticker dashboard."""

from datetime import date
from decimal import Decimal

from src.adapters.cli.view_ticker_flow_display import (
    _select_foreign_flow_points,
    _window_buy_sell_days,
    _window_net,
)
from src.domain.entities.broker_flow import ForeignFlowPoint


def _point(
    day: int,
    net_val: str,
    *,
    source: str = "stockbit",
    net_lot: int = 0,
) -> ForeignFlowPoint:
    return ForeignFlowPoint(
        ticker="BBCA",
        date=date(2026, 7, day),
        net_val=Decimal(net_val),
        net_lot=net_lot,
        avg_price=Decimal("6000"),
        source=source,
    )


def test_select_foreign_flow_points_prefers_stockbit_over_idx():
    points, source = _select_foreign_flow_points(
        {
            "idx": [_point(22, "100", source="idx")],
            "stockbit": [_point(23, "-50", source="stockbit")],
        }
    )
    assert source == "stockbit"
    assert len(points) == 1
    assert points[0].net_val == Decimal("-50")


def test_select_foreign_flow_points_falls_back_to_idx():
    points, source = _select_foreign_flow_points(
        {"stockbit": [], "idx": [_point(23, "10", source="idx")]}
    )
    assert source == "idx"
    assert points[0].source == "idx"


def test_window_net_and_buy_sell_days():
    points = [
        _point(19, "100"),
        _point(20, "-20"),
        _point(21, "-30"),
        _point(22, "40"),
        _point(23, "-10"),
    ]
    assert _window_net(points, 5) == Decimal("80")
    assert _window_buy_sell_days(points, 5) == (2, 3)
    assert _window_net(points, 2) == Decimal("30")
