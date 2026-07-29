"""Unit tests for TUI row formatter for view ticker top-brokers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli.view_ticker_top_brokers_display import format_ticker_top_brokers_rows
from src.domain.entities.broker_flow import BrokerType


def test_format_ticker_top_brokers_rows_buyers_and_sellers():
    result = SimpleNamespace(
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
    rows = format_ticker_top_brokers_rows(result, limit=10)
    assert len(rows) == 2
    buy, sell = rows
    assert buy.code == "AK"
    assert buy.role == "buy"
    assert buy.type_label == "Foreign"
    assert buy.day_net == "1.20B"
    assert buy.as_of == "2026-03-01"
    assert sell.code == "YP"
    assert sell.role == "sell"
    assert sell.type_label == "Local"
    assert sell.day_net == "-500.00M"
    assert len(sell.name) <= 20
