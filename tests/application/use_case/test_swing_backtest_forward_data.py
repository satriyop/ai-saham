from datetime import date, timedelta
from decimal import Decimal

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestUseCase,
)
from tests.application.use_case.swing_backtest_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    _base_candles,
    _summary,
)


def test_swing_backtest_no_forward_data_increments_skipped_no_forward_data():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    candles = _base_candles("BBCA", base)
    candles = [c for c in candles if c.date <= signal_date]
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]
    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
    )

    response = use_case.execute(SwingBacktestRequest(
        tickers=["BBCA"],
        start_date=signal_date,
        end_date=exit_date,
        capital=Decimal("1000000"),
        risk_pct=Decimal("0.01"),
        max_positions=1,
        min_net_buy_days=1,
        cost_bps=Decimal("0"),
    ))

    assert response.trade_count == 0
    assert response.skipped_no_forward_data == 1
