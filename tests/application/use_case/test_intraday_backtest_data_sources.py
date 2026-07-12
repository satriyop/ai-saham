from decimal import Decimal
from unittest.mock import MagicMock

from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from src.domain.entities.candle import Candle
from src.infrastructure.persistence.sqlite_iev_repository import IEVSnapshot
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
    _history,
    _history_with_prev,
)


def test_proxy_does_not_require_backed_accumulation_when_no_broker_data():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today, summaries=[])
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.opening_broker_backing_tag is None
    assert trade.opening_broker_backing_score is None
    assert trade.opening_broker_buy_streak is None
    assert trade.exit_reason == "target"


def test_insufficient_history_skips_ticker_silently():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    short_history = _history(TICKER, PREV_DAY, days=10)
    use_case = _build(today, history=short_history)

    resp = use_case.execute(_default_request())
    assert resp.trade_count == 0


def test_backtest_uses_get_ncp_snapshot():
    tickers = ["BBCA", "BBRI"]
    today_candles = [
        _candle(t, TRADE_DAY, Decimal("100"), Decimal("106"), Decimal("99"), Decimal("101"))
        for t in tickers
    ]
    history: list[Candle] = []
    for t in tickers:
        history.extend(_history_with_prev(t, PREV_DAY))

    market = InMemoryMarketRepository(history + today_candles)
    broker = InMemoryBrokerRepository(
        _backed_summaries("BBCA", PREV_DAY) + _backed_summaries("BBRI", PREV_DAY)
    )

    iev_repo = MagicMock()
    iev_repo.has_snapshot.return_value = True
    iev_repo.get_ncp_snapshot.return_value = [
        IEVSnapshot(date=TRADE_DAY, ticker="BBCA", iev=450_000, rank=1, iep=5_900)
    ]
    iev_repo.get_snapshot_dates.return_value = [TRADE_DAY]

    uc = IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=StubIndicatorRegistry(),
        iev_repository=iev_repo,
    )

    resp = uc.execute(IntradayBacktestRequest(
        tickers=tickers,
        start_date=TRADE_DAY,
        end_date=TRADE_DAY,
        capital=Decimal("100000000"),
        risk_pct=Decimal("0.01"),
        max_daily_positions=3,
        cost_bps=Decimal("0"),
        history_days=30,
    ))

    iev_repo.get_ncp_snapshot.assert_called_once()
    iev_repo.get_snapshot.assert_not_called()

    traded_tickers = {t.ticker for t in resp.trades}
    assert "BBCA" in traded_tickers
    assert "BBRI" not in traded_tickers
