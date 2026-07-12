from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.swing_backtest_use_case import (
    DEFAULT_SWING_COST_BPS,
    SwingBacktestRequest,
    SwingBacktestUseCase,
)
from tests.application.use_case.swing_backtest_fixtures import (
    MockBrokerRepository,
    MockMarketRepository,
    _base_candles,
    _summary,
)


def test_swing_backtest_default_applies_transaction_costs():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]
    use_case = SwingBacktestUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(_base_candles("BBCA", base)),
    )

    response = use_case.execute(SwingBacktestRequest(
        tickers=["BBCA"],
        start_date=signal_date,
        end_date=exit_date,
        capital=Decimal("1000000"),
        risk_pct=Decimal("0.01"),
        max_positions=1,
        min_net_buy_days=1,
    ))

    assert response.cost_bps == DEFAULT_SWING_COST_BPS
    assert response.trade_count == 1
    assert response.total_return_pct == 0.918
    assert response.final_equity == Decimal("1009180.000")
    assert response.trades[0].net_return_pct == 4.59


def test_swing_backtest_respects_max_positions():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    candles = _base_candles("BBCA", base) + _base_candles("BBRI", base)
    summaries = [
        _summary(ticker, base + timedelta(days=i), Decimal("110"))
        for ticker in ("BBCA", "BBRI")
        for i in range(18, 25)
    ]
    use_case = SwingBacktestUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )

    response = use_case.execute(SwingBacktestRequest(
        tickers=["BBCA", "BBRI"],
        start_date=signal_date,
        end_date=exit_date,
        capital=Decimal("1000000"),
        risk_pct=Decimal("0.01"),
        max_positions=1,
        min_net_buy_days=1,
        cost_bps=Decimal("0"),
    ))

    assert response.trade_count == 1
    assert len({trade.ticker for trade in response.trades}) == 1
