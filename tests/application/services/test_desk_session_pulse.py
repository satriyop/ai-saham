"""desk_session_pulse: Net5 / buy-streak / Δ1 from session nets."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.services.broker_desk_from_daily_flow import desk_session_pulse
from src.domain.entities.broker_flow import BrokerDailyFlow


def _flow(d: date, net: str, ticker: str = "BBCA") -> BrokerDailyFlow:
    n = Decimal(net)
    buy = n if n > 0 else Decimal("0")
    sell = -n if n < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code="AK",
        broker_name="Alpha",
        date=d,
        buy_lot=1,
        sell_lot=0,
        net_lot=1,
        buy_value=buy,
        sell_value=sell,
        net_value=n,
        avg_buy_price=Decimal("1"),
        avg_sell_price=Decimal("1"),
        avg_price=Decimal("1"),
        buy_pct=0.0,
        sell_pct=0.0,
        source="test",
    )


def test_pulse_net5_streak_delta1():
    flows = [
        _flow(date(2026, 7, 20), "100"),
        _flow(date(2026, 7, 21), "200"),
        _flow(date(2026, 7, 22), "-50"),  # breaks older streak
        _flow(date(2026, 7, 23), "10"),
        _flow(date(2026, 7, 24), "20"),
        _flow(date(2026, 7, 25), "30"),  # streak 3
    ]
    p = desk_session_pulse(flows, net_window=5)
    assert p is not None
    assert p.as_of == date(2026, 7, 25)
    assert p.day_net == Decimal("30")
    # last 5 sessions: -50+10+20+30+200? wait sorted: 21,22,23,24,25 = 200-50+10+20+30 = 210
    # days: 20,21,22,23,24,25 — last 5 = 21..25 = 200-50+10+20+30 = 210
    assert p.net5 == Decimal("210")
    assert p.sessions_in_net5 == 5
    assert p.buy_streak == 3
    assert p.delta1 == Decimal("10")  # 30 - 20


def test_pulse_streak_zero_when_latest_sell():
    flows = [
        _flow(date(2026, 7, 24), "100"),
        _flow(date(2026, 7, 25), "-10"),
    ]
    p = desk_session_pulse(flows)
    assert p is not None
    assert p.buy_streak == 0
    assert p.delta1 == Decimal("-110")


def test_pulse_empty():
    assert desk_session_pulse([]) is None
