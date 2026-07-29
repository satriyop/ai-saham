"""Unit tests for TUI row formatter for view ticker top-brokers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli.view_ticker_top_brokers_display import format_ticker_top_brokers_rows
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
    assert buy.net5 == "—"
    assert buy.streak == "—"
    assert buy.delta1 == "—"
    assert buy.has_pulse is False
    assert sell.code == "YP"
    assert sell.role == "sell"
    assert sell.type_label == "Local"
    assert sell.day_net == "-500.00M"
    assert len(sell.name) <= 20


def test_format_ticker_top_brokers_rows_with_stock_scoped_pulse():
    pulse = DeskSessionPulse(
        as_of=date(2026, 3, 5),
        day_net=Decimal("30000000"),
        net5=Decimal("210000000"),
        sessions_in_net5=5,
        buy_streak=3,
        delta1=Decimal("10000000"),
    )
    rows = format_ticker_top_brokers_rows(
        _result(),
        limit=10,
        pulses={"AK": pulse},
    )
    buy = rows[0]
    assert buy.code == "AK"
    assert buy.has_pulse is True
    assert buy.as_of == "2026-03-05"  # pulse as_of, not summary date
    assert buy.day_net == "30.00M"
    assert buy.net5 == "210.00M"
    assert buy.streak == "3"
    assert buy.delta1 == "+10.00M"
    # YP has no pulse — keeps summary day net
    sell = rows[1]
    assert sell.has_pulse is False
    assert sell.as_of == "2026-03-01"
    assert sell.net5 == "—"
