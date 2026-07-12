from datetime import timedelta
from decimal import Decimal

from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from tests.application.use_case.intraday_backtest_fixtures import (
    PREV_DAY,
    TICKER,
    TRADE_DAY,
    InMemoryBrokerRepository,
    InMemoryMarketRepository,
    StubIndicatorRegistry,
    _backed_summaries,
    _build,
    _candle,
    _default_request,
    _history_with_prev,
)


def test_proxy_does_not_replay_tick_friction_gate():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("100"),
        close=Decimal("101"),
    )
    history = _history_with_prev(
        TICKER,
        PREV_DAY,
        prev_close=Decimal("100"),
        prev_high=Decimal("101"),
    )
    registry = StubIndicatorRegistry(atr=Decimal("1"))
    use_case = _build(today, history=history, registry=registry)

    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.stop_price == Decimal("99")
    assert trade.target_price == Decimal("101")
    assert trade.exit_reason == "target"


def test_include_wait_false_skips_wait_decisions():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    registry = StubIndicatorRegistry(sma=Decimal("101"))
    use_case = _build(today, registry=registry)
    resp = use_case.execute(_default_request(include_wait=False))

    assert resp.trade_count == 0


def test_include_wait_true_trades_wait_decisions():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    registry = StubIndicatorRegistry(sma=Decimal("101"))
    use_case = _build(today, registry=registry)
    resp = use_case.execute(_default_request(include_wait=True))

    assert resp.trade_count == 1
    assert resp.trades[0].decision == "WAIT"


def test_max_daily_positions_one_caps_trades_per_day():
    tickers = ["BBCA", "BBRI"]
    today_candles = [
        _candle(t, TRADE_DAY, Decimal("100"), Decimal("106"), Decimal("99"), Decimal("101"))
        for t in tickers
    ]
    history = []
    summaries = []
    for t in tickers:
        history.extend(_history_with_prev(t, PREV_DAY))
        summaries.extend(_backed_summaries(t, PREV_DAY))

    market = InMemoryMarketRepository(history + today_candles)
    broker = InMemoryBrokerRepository(summaries)
    use_case = IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=StubIndicatorRegistry(),
    )

    resp = use_case.execute(IntradayBacktestRequest(
        tickers=tickers,
        start_date=TRADE_DAY,
        end_date=TRADE_DAY,
        max_daily_positions=1,
        cost_bps=Decimal("0"),
        history_days=30,
    ))

    assert resp.trade_count == 1


def test_ranking_picks_higher_opening_broker_backing_score_when_capped():
    tickers = ["BBCA", "BBRI"]
    today_candles = [
        _candle(t, TRADE_DAY, Decimal("100"), Decimal("106"), Decimal("99"), Decimal("101"))
        for t in tickers
    ]
    history = []
    for t in tickers:
        history.extend(_history_with_prev(t, PREV_DAY))

    summaries = []
    summaries.extend(_backed_summaries("BBCA", PREV_DAY, days=7))
    for i in range(3):
        day = PREV_DAY - timedelta(days=6 - i)
        summaries.append(BrokerSummary(
            ticker="BBRI",
            date=day,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("100000"),
            foreign_sell_value=Decimal("1000000"),
            foreign_buy_lot=1_000,
            foreign_sell_lot=10_000,
            total_value=Decimal("2000000"),
            total_lot=20_000,
        ))
    for i in range(4):
        day = PREV_DAY - timedelta(days=3 - i)
        summaries.append(BrokerSummary(
            ticker="BBRI",
            date=day,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("1000000"),
            foreign_sell_value=Decimal("100000"),
            foreign_buy_lot=10_000,
            foreign_sell_lot=1_000,
            total_value=Decimal("2000000"),
            total_lot=20_000,
        ))

    market = InMemoryMarketRepository(history + today_candles)
    broker = InMemoryBrokerRepository(summaries)
    use_case = IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=StubIndicatorRegistry(),
    )

    resp = use_case.execute(IntradayBacktestRequest(
        tickers=tickers,
        start_date=TRADE_DAY,
        end_date=TRADE_DAY,
        max_daily_positions=1,
        cost_bps=Decimal("0"),
        history_days=30,
    ))

    assert resp.trade_count == 1
    chosen = resp.trades[0]
    assert chosen.ticker == "BBCA"
    assert chosen.opening_broker_backing_score is not None
    assert chosen.opening_broker_backing_tag == "BACKED"
