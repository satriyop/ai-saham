"""Tests for desk ranking helpers."""

from datetime import date
from decimal import Decimal

from src.application.services.broker_desk_from_daily_flow import (
    aggregate_desk_by_date,
    rank_tickers_for_desk,
)
from src.domain.entities.broker_flow import BrokerDailyFlow


def _flow(ticker: str, d: date, net: str, code: str = "AK") -> BrokerDailyFlow:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=code,
        broker_name="UBS",
        date=d,
        buy_lot=1 if buy else 0,
        sell_lot=1 if sell else 0,
        net_lot=1 if buy else -1,
        buy_value=buy,
        sell_value=sell,
        net_value=value,
        avg_buy_price=Decimal("0"),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal("0"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def test_rank_tickers_for_desk():
    d = date(2026, 7, 23)
    flows = [
        _flow("AMMN", d, "100"),
        _flow("BBCA", d, "-50"),
        _flow("BBRI", d, "30"),
    ]
    buyers, sellers = rank_tickers_for_desk(flows, limit=10)
    assert [b.ticker for b in buyers] == ["AMMN", "BBRI"]
    assert [s.ticker for s in sellers] == ["BBCA"]


def test_aggregate_desk_by_date():
    flows = [
        _flow("BBCA", date(2026, 7, 22), "10"),
        _flow("BBRI", date(2026, 7, 22), "-3"),
        _flow("BBCA", date(2026, 7, 23), "5"),
    ]
    days = aggregate_desk_by_date(flows)
    assert len(days) == 2
    assert days[0].net_value == Decimal("7")
    assert days[0].ticker_count == 2
    assert days[1].net_value == Decimal("5")
