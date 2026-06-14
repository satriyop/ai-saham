"""Tests for accumulation CLI helper logic."""

from datetime import date
from decimal import Decimal

from src.adapters.cli.accumulation_commands import _build_screen_broker_quality
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType


class FakeBrokerSummaryRepository:
    def __init__(self, summaries):
        self._summaries = summaries

    def get_broker_summaries(self, ticker: str, start_date=None, end_date=None):
        return [
            summary
            for summary in self._summaries
            if summary.ticker == ticker
            and (start_date is None or summary.date >= start_date)
            and (end_date is None or summary.date <= end_date)
        ]


def _tx(
    code: str,
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=broker_type,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _summary(
    day: date,
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
) -> BrokerSummary:
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source="stockbit",
    )


def test_screen_broker_quality_counts_local_noise_brokers():
    quality = _build_screen_broker_quality(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository([
            _summary(
                date(2026, 6, 12),
                top_buyers=(
                    _tx("YP", "100000000", "10000000", BrokerType.LOCAL),
                    _tx("XC", "70000000", "5000000", BrokerType.LOCAL),
                ),
                top_sellers=(_tx("AK", "5000000", "25000000"),),
            )
        ]),
        as_of_date=date(2026, 6, 12),
    )

    assert quality is not None
    assert quality.label == "noise+"
    assert quality.noise_flow == Decimal("155000000")
    assert quality.smart_flow == Decimal("-20000000")
    assert quality.to_dict()["source"] == "stockbit"


def test_screen_broker_quality_marks_smart_selling_pressure():
    quality = _build_screen_broker_quality(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository([
            _summary(
                date(2026, 6, 12),
                top_buyers=(_tx("CC", "40000000", "5000000"),),
                top_sellers=(_tx("BK", "5000000", "90000000"),),
            )
        ]),
        as_of_date=date(2026, 6, 12),
    )

    assert quality is not None
    assert quality.label == "smart-"
    assert quality.smart_flow == Decimal("-85000000")
