from datetime import date, timedelta
from decimal import Decimal

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestUseCase,
)
from tests.application.use_case.swing_backtest_fixtures import (
    FailingRiskEngine,
    FakeRiskEngine,
    MockBrokerRepository,
    MockMarketRepository,
    _base_candles,
    _summary,
)


def test_swing_backtest_records_rejected_candidate_observations():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]
    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(_base_candles("BBCA", base)),
    )

    response = use_case.execute(SwingBacktestRequest(
        tickers=["BBCA"],
        start_date=signal_date,
        end_date=exit_date,
        setup="smart-money-confirmed",
        capital=Decimal("1000000"),
        risk_pct=Decimal("0.01"),
        max_positions=1,
        min_net_buy_days=1,
        cost_bps=Decimal("0"),
    ))

    assert response.trade_count == 0
    assert response.candidate_observations
    observation = response.candidate_observations[0]
    assert observation.setup_match in {"PARTIAL", "NO_MATCH"}
    assert observation.forward_return_pct == 5.0
    summary = response.attribution_summary.to_dict()
    assert any(
        stat["dimension"] == "candidate_setup_match"
        for stat in summary["candidate_group_stats"]
    )


def test_swing_backtest_records_risk_and_trade_setup_attribution():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]
    risk_engine = FakeRiskEngine()
    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(_base_candles("BBCA", base)),
        risk_engine=risk_engine,
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

    assert response.trade_count == 1
    trade = response.trades[0]
    assert trade.risk_status == "OPEN"
    assert trade.risk_gate is None
    assert trade.risk_confidence == 0
    assert trade.trade_setup_action is not None
    assert risk_engine.contexts[0].ticker == "BBCA"
    assert risk_engine.contexts[0].snapshot_date == signal_date


def test_swing_backtest_keeps_trade_when_risk_attribution_fails():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]
    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(_base_candles("BBCA", base)),
        risk_engine=FailingRiskEngine(),
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

    assert response.trade_count == 1
    assert response.trades[0].risk_status is None
    assert response.trades[0].trade_setup_action is None
