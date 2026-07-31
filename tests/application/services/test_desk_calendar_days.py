"""Desk calendar day builder — top stock · net · B/S per session."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.services.broker_desk_from_daily_flow import build_desk_calendar_days
from src.domain.entities.broker_flow import BrokerDailyFlow


def _flow(
    ticker: str,
    d: date,
    net: str,
    *,
    buy: str | None = None,
    sell: str | None = None,
    code: str = "YP",
) -> BrokerDailyFlow:
    nv = Decimal(net)
    bv = Decimal(buy) if buy is not None else (nv if nv > 0 else Decimal("0"))
    sv = Decimal(sell) if sell is not None else (-nv if nv < 0 else Decimal("0"))
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=code,
        broker_name="YP",
        date=d,
        buy_lot=1 if bv else 0,
        sell_lot=1 if sv else 0,
        net_lot=1 if nv > 0 else -1,
        buy_value=bv,
        sell_value=sv,
        net_value=nv,
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal("1000"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def test_calendar_top_stock_is_strongest_net_buyer():
    d = date(2026, 7, 29)
    flows = [
        _flow("AMMN", d, "100", buy="100"),
        _flow("BUMI", d, "50", buy="50"),
        _flow("BBCA", d, "-20", sell="20"),
    ]
    days = build_desk_calendar_days(flows, max_sessions=22)
    assert len(days) == 1
    assert days[0].top_ticker == "AMMN"
    assert days[0].net_value == Decimal("130")
    assert days[0].buy_value == Decimal("150")
    assert days[0].sell_value == Decimal("20")
    assert days[0].ticker_count == 3


def test_calendar_truncates_to_max_sessions():
    base = date(2026, 7, 1)
    flows = []
    for i in range(30):
        flows.append(_flow("AMMN", base + timedelta(days=i), "10"))
    days = build_desk_calendar_days(flows, max_sessions=5)
    assert len(days) == 5
    assert days[-1].date == base + timedelta(days=29)
