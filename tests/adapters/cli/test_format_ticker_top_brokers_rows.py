"""Unit tests for TUI row formatter for view ticker top-brokers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli.view_ticker_top_brokers_display import (
    format_netx_display,
    format_ticker_top_brokers_rows,
)
from src.application.services.broker_desk_from_daily_flow import DeskSessionPulse
from src.domain.entities.broker_flow import BrokerType


def _result():
    return SimpleNamespace(
        ticker="BBCA",
        date=date(2026, 3, 1),
        top_buyers=[
            SimpleNamespace(
                broker_code="ak",
                broker_name="Desk Alpha",
                broker_type=BrokerType.FOREIGN,
                is_foreign=True,
                net_value=Decimal("1200000000"),
                net_lot=100,
            )
        ],
        top_sellers=[
            SimpleNamespace(
                broker_code="yp",
                broker_name="Desk YP Long Name Truncated",
                broker_type=BrokerType.LOCAL,
                is_foreign=False,
                net_value=Decimal("-500000000"),
                net_lot=-50,
            )
        ],
    )


def test_format_ticker_top_brokers_rows_buyers_and_sellers():
    rows = format_ticker_top_brokers_rows(_result(), limit=10)
    assert len(rows) == 2
    buy, sell = rows
    assert buy.code == "AK"
    assert buy.role == "buy"
    assert buy.type_label == "Foreign"
    assert buy.day_net == "1.20B"
    assert buy.as_of == "2026-03-01"
    assert buy.net3 == "—"
    assert buy.net5 == "—"
    assert buy.net7 == "—"
    assert buy.net10 == "—"
    assert buy.net20 == "—"
    assert buy.streak == "—"
    assert buy.delta1 == "—"
    assert buy.has_pulse is False
    assert not hasattr(buy, "name") or getattr(buy, "name", None) is None
    assert sell.code == "YP"
    assert sell.role == "sell"
    assert sell.type_label == "Local"
    assert sell.day_net == "-500.00M"


def test_format_netx_display_partial_marks_used_over_window():
    assert format_netx_display(Decimal("60"), sessions_used=4, window=20) == "60.00*(4/20)"
    assert format_netx_display(Decimal("60"), sessions_used=20, window=20) == "60.00"
    assert format_netx_display(None, sessions_used=0, window=5) == "—"


def test_format_ticker_top_brokers_rows_with_stock_scoped_pulse():
    pulse = DeskSessionPulse(
        as_of=date(2026, 3, 5),
        day_net=Decimal("30000000"),
        net5=Decimal("210000000"),
        sessions_in_net5=5,
        buy_streak=3,
        delta1=Decimal("10000000"),
        window_nets=(
            (3, Decimal("60000000"), 3),
            (5, Decimal("210000000"), 5),
            (7, Decimal("250000000"), 6),
            (10, Decimal("250000000"), 6),
            (20, Decimal("250000000"), 6),
        ),
    )
    rows = format_ticker_top_brokers_rows(
        _result(),
        limit=10,
        pulses={"AK": pulse},
    )
    buy = rows[0]
    assert buy.code == "AK"
    assert buy.has_pulse is True
    assert buy.has_partial_netx is True
    assert buy.as_of == "2026-03-05"  # pulse as_of, not summary date
    assert buy.day_net == "30.00M"
    assert buy.net3 == "60.00M"  # full 3/3
    assert buy.net5 == "210.00M"  # full 5/5
    assert buy.net7 == "250.00M*(6/7)"
    assert buy.net10 == "250.00M*(6/10)"
    assert buy.net20 == "250.00M*(6/20)"
    assert buy.partial_windows == (7, 10, 20)
    assert buy.sessions_cached == 6
    assert buy.streak == "3"
    assert buy.delta1 == "+10.00M"
    # YP has no pulse — keeps summary day net
    sell = rows[1]
    assert sell.has_pulse is False
    assert sell.has_partial_netx is False
    assert sell.as_of == "2026-03-01"
    assert sell.net5 == "—"
    assert sell.net20 == "—"
