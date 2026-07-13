from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestUseCase,
)
from tests.application.use_case.swing_backtest_fixtures import (
    FakeMarketContextProvider,
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    _base_candles,
    _flat_candle,
    _summary,
)


def test_swing_backtest_can_filter_entries_by_allowed_regimes():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]
    benchmark_candles = [
        _flat_candle("IHSG", base - timedelta(days=60 - i), Decimal(1000 + i))
        for i in range(86)
    ]
    broker_repo = MockBrokerRepository(summaries)
    market_repo = MockMarketRepository(
        _base_candles("BBCA", base) + benchmark_candles
    )
    from src.domain.value_objects.market_context import MarketContext, MarketRegime
    fake_context = MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=signal_date,
    )
    fake_context_exit = MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=exit_date,
    )
    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=broker_repo,
        market_repository=market_repo,
        rules_loader=FakeRulesLoader(),
        market_context_provider=FakeMarketContextProvider({
            signal_date: fake_context,
            exit_date: fake_context_exit,
        }),
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
        benchmark_ticker="IHSG",
        allowed_regimes=("RISK_OFF",),
    ))

    assert response.trade_count == 0
    assert response.skipped_by_regime == 1
    assert response.regime_by_date


def test_swing_backtest_provider_is_not_called_when_regime_is_not_requested():
    from src.domain.value_objects.market_context import MarketContext, MarketRegime

    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)

    candles = _base_candles("BBCA", base)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]

    fake_context = MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=signal_date,
    )
    provider = FakeMarketContextProvider({signal_date: fake_context})

    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        market_context_provider=provider,
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
        include_regime=False,
        allowed_regimes=(),
    ))

    assert provider.calls == []
    assert response.regime_by_date == {}


def test_swing_backtest_provider_is_called_when_include_regime_is_true():
    from src.domain.value_objects.market_context import MarketContext, MarketRegime

    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)

    candles = _base_candles("BBCA", base)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]

    fake_context = MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=signal_date,
    )
    provider = FakeMarketContextProvider({signal_date: fake_context})

    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        market_context_provider=provider,
    )

    response = use_case.execute(SwingBacktestRequest(
        tickers=["bbca"],
        start_date=signal_date,
        end_date=exit_date,
        capital=Decimal("1000000"),
        risk_pct=Decimal("0.01"),
        max_positions=1,
        min_net_buy_days=1,
        cost_bps=Decimal("0"),
        include_regime=True,
        allowed_regimes=(),
        benchmark_ticker="ihsg",
    ))

    assert len(provider.calls) == 1
    assert provider.calls[0]["tickers"] == ["BBCA"]
    assert provider.calls[0]["benchmark_ticker"] == "ihsg"
    assert response.regime_by_date == {signal_date: fake_context}


def test_swing_backtest_provider_is_called_when_allowed_regimes_non_empty():
    from src.domain.value_objects.market_context import MarketContext, MarketRegime

    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)

    candles = _base_candles("BBCA", base)
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal("110"))
        for i in range(18, 25)
    ]

    fake_context = MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=signal_date,
    )
    provider = FakeMarketContextProvider({signal_date: fake_context})

    use_case = SwingBacktestUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        market_context_provider=provider,
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
        include_regime=False,
        allowed_regimes=("NEUTRAL",),
    ))

    assert len(provider.calls) == 1
    assert response.regime_by_date == {signal_date: fake_context}


def test_swing_backtest_raises_when_regime_requested_without_provider():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)

    candles = _base_candles("BBCA", base)
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

    with pytest.raises(ValueError, match="market_context_provider is required"):
        use_case.execute(SwingBacktestRequest(
            tickers=["BBCA"],
            start_date=signal_date,
            end_date=exit_date,
            capital=Decimal("1000000"),
            risk_pct=Decimal("0.01"),
            max_positions=1,
            min_net_buy_days=1,
            cost_bps=Decimal("0"),
            include_regime=True,
        ))


def test_swing_backtest_raises_when_allowed_regimes_without_provider():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)

    candles = _base_candles("BBCA", base)
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

    with pytest.raises(ValueError, match="market_context_provider is required"):
        use_case.execute(SwingBacktestRequest(
            tickers=["BBCA"],
            start_date=signal_date,
            end_date=exit_date,
            capital=Decimal("1000000"),
            risk_pct=Decimal("0.01"),
            max_positions=1,
            min_net_buy_days=1,
            cost_bps=Decimal("0"),
            include_regime=False,
            allowed_regimes=("NEUTRAL",),
        ))
