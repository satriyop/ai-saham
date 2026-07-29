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


def test_pulse_multi_window_netx():
    from src.application.services.broker_desk_from_daily_flow import STOCK_DESK_NET_WINDOWS

    # 20 sessions of +1 each → NetX == min(X, 20)
    flows = [
        _flow(date(2026, 6, d), "1")
        for d in range(1, 21)  # June 1..20
    ]
    p = desk_session_pulse(flows, net_windows=STOCK_DESK_NET_WINDOWS)
    assert p is not None
    assert p.day_net == Decimal("1")
    assert p.net_for(3) == Decimal("3")
    assert p.net_for(5) == Decimal("5")
    assert p.net5 == Decimal("5")
    assert p.net_for(7) == Decimal("7")
    assert p.net_for(10) == Decimal("10")
    assert p.net_for(20) == Decimal("20")
    assert p.sessions_for(20) == 20
    assert [w for w, _n, _s in p.window_nets] == list(STOCK_DESK_NET_WINDOWS)


def test_pulse_multi_window_partial_history():
    flows = [
        _flow(date(2026, 7, 23), "10"),
        _flow(date(2026, 7, 24), "20"),
        _flow(date(2026, 7, 25), "30"),
    ]
    p = desk_session_pulse(flows, net_windows=(3, 5, 7, 10, 20))
    assert p is not None
    # Only 3 sessions exist — NetX uses min(X, n)
    assert p.net_for(3) == Decimal("60")
    assert p.net_for(5) == Decimal("60")
    assert p.net_for(20) == Decimal("60")
    assert p.sessions_for(20) == 3
