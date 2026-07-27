from decimal import Decimal

from tests.application.use_case.intraday_backtest_fixtures import (
    TICKER,
    TRADE_DAY,
    _build,
    _candle,
    _default_request,
)


def test_cost_arithmetic_and_gross_vs_net_for_winner():
    today = _candle(
        TICKER,
        TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request(cost_bps=Decimal("20")))

    assert resp.trade_count == 1
    trade = resp.trades[0]

    shares = Decimal(trade.shares)
    entry = trade.entry_price
    exit_p = trade.exit_price
    entry_cost = shares * entry * Decimal("20") / Decimal("10000")
    exit_cost = shares * exit_p * Decimal("20") / Decimal("10000")
    expected_cost_total = entry_cost + exit_cost
    expected_pnl = (exit_p - entry) * shares - expected_cost_total

    assert trade.cost_total == expected_cost_total
    assert trade.pnl == expected_pnl
    assert trade.gross_return_pct > trade.net_return_pct
    assert trade.gross_return_pct == 5.0


def test_r_multiple_equals_pnl_over_initial_risk():
    today = _candle(
        TICKER,
        TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    trade = resp.trades[0]
    initial_risk = Decimal(trade.shares) * (trade.entry_price - trade.stop_price)
    expected_r = round(float(trade.pnl / initial_risk), 3)

    assert trade.r_multiple == expected_r
