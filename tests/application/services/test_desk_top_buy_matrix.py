"""Tests for desk top-5 multi-window net-buy matrix helpers."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.services.broker_desk_from_daily_flow import (
    desk_ticker_buy_streak,
    lot_weighted_avg_buy_price,
    rank_desk_top_buy_matrix,
)
from src.domain.entities.broker_flow import BrokerDailyFlow


def _flow(
    ticker: str,
    d: date,
    net: str,
    *,
    buy_lot: int = 10,
    avg_buy: str = "1000",
    code: str = "YP",
) -> BrokerDailyFlow:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=code,
        broker_name="YP",
        date=d,
        buy_lot=buy_lot if buy else 0,
        sell_lot=buy_lot if sell else 0,
        net_lot=buy_lot if buy else -buy_lot,
        buy_value=buy,
        sell_value=sell,
        net_value=value,
        avg_buy_price=Decimal(avg_buy),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal(avg_buy),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def test_lot_weighted_avg_buy_price():
    d0 = date(2026, 7, 20)
    d1 = date(2026, 7, 21)
    rows = [
        _flow("AMMN", d0, "100", buy_lot=10, avg_buy="1000"),
        _flow("AMMN", d1, "200", buy_lot=30, avg_buy="1200"),
    ]
    avg = lot_weighted_avg_buy_price(rows)
    # (1000*10 + 1200*30) / 40 = 1150
    assert avg == Decimal("1150")


def test_lot_weighted_skips_zero_buy_lot():
    d0 = date(2026, 7, 20)
    rows = [_flow("AMMN", d0, "-50", buy_lot=0, avg_buy="999")]
    assert lot_weighted_avg_buy_price(rows) is None


def test_desk_ticker_buy_streak_breaks_on_sell():
    base = date(2026, 7, 20)
    flows = [
        _flow("AMMN", base, "10"),
        _flow("AMMN", base + timedelta(days=1), "10"),
        _flow("AMMN", base + timedelta(days=2), "-5"),  # break
        _flow("AMMN", base + timedelta(days=3), "10"),
        _flow("AMMN", base + timedelta(days=4), "10"),
        # desk also active on other names so sessions include sell day
        _flow("BBCA", base + timedelta(days=2), "1"),
    ]
    assert desk_ticker_buy_streak(flows, "AMMN") == 2  # last two buys only


def test_desk_ticker_buy_streak_zero_when_latest_not_buy():
    base = date(2026, 7, 20)
    flows = [
        _flow("AMMN", base, "10"),
        _flow("AMMN", base + timedelta(days=1), "-1"),
    ]
    assert desk_ticker_buy_streak(flows, "AMMN") == 0


def test_desk_ticker_buy_streak_breaks_on_missing_session():
    """Desk traded other names; ticker absent that session breaks streak."""
    base = date(2026, 7, 20)
    flows = [
        _flow("AMMN", base, "10"),
        _flow("BBCA", base + timedelta(days=1), "5"),  # AMMN missing
        _flow("AMMN", base + timedelta(days=2), "10"),
    ]
    assert desk_ticker_buy_streak(flows, "AMMN") == 1


def test_rank_matrix_1s_order_and_fields():
    d = date(2026, 7, 23)
    flows = [
        _flow("AMMN", d, "100", buy_lot=20, avg_buy="9000"),
        _flow("BUMI", d, "50", buy_lot=100, avg_buy="150"),
        _flow("BBRI", d, "-10", buy_lot=0, avg_buy="0"),
    ]
    cols = rank_desk_top_buy_matrix(flows, windows=(1, 3), limit=5)
    c1 = cols[1]
    assert [c.ticker for c in c1] == ["AMMN", "BUMI"]
    assert c1[0].avg_buy_price == Decimal("9000")
    assert c1[0].buy_streak == 1
    assert c1[0].is_partial is False
    assert c1[0].sessions_used == 1
    # window 3 only has 1 session → partial
    assert cols[3][0].is_partial is True
    assert cols[3][0].sessions_used == 1


def test_rank_matrix_multi_session_net_sum():
    base = date(2026, 7, 20)
    flows = []
    for i in range(5):
        d = base + timedelta(days=i)
        flows.append(_flow("AMMN", d, "10", buy_lot=10, avg_buy="1000"))
        flows.append(_flow("BUMI", d, "5", buy_lot=50, avg_buy="100"))
    cols = rank_desk_top_buy_matrix(flows, windows=(1, 5), limit=5)
    assert cols[1][0].ticker == "AMMN"
    assert cols[1][0].net_value == Decimal("10")
    assert cols[5][0].ticker == "AMMN"
    assert cols[5][0].net_value == Decimal("50")
    assert cols[5][0].buy_streak == 5
    assert cols[5][0].is_partial is False
