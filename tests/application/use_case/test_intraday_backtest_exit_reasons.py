from decimal import Decimal

from tests.application.use_case.intraday_backtest_fixtures import (
    TICKER,
    TRADE_DAY,
    _build,
    _candle,
    _default_request,
)


def test_exit_reason_target_when_high_reaches_prev_high():
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

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.entry_price == Decimal("100")
    assert trade.opening_price == Decimal("100")
    assert trade.exit_reason == "target"
    assert trade.exit_price == Decimal("105")
    assert any("Tick-friction and regime gates are NOT replayed" in w for w in resp.warnings)
    assert trade.target_price == Decimal("105")
    assert trade.stop_price == Decimal("98")
    assert trade.same_day_both_breached is False


def test_exit_reason_stop_when_low_breaches_stop():
    today = _candle(
        TICKER,
        TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("104"),
        low=Decimal("97"),
        close=Decimal("99"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == Decimal("98")
    assert trade.same_day_both_breached is False


def test_exit_reason_close_when_neither_stop_nor_target_hit():
    today = _candle(
        TICKER,
        TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("104"),
        low=Decimal("99"),
        close=Decimal("102"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "close"
    assert trade.exit_price == Decimal("102")


def test_exit_reason_both_assume_stop_when_high_and_low_both_breach():
    today = _candle(
        TICKER,
        TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("97"),
        close=Decimal("100"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "both_assume_stop"
    assert trade.exit_price == Decimal("98")
    assert trade.same_day_both_breached is True
