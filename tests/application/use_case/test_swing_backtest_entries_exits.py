from datetime import date, timedelta
from decimal import Decimal

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
    _ohlc,
    _summary,
)


def test_swing_backtest_opens_signal_and_exits_at_target():
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
        include_regime=True,
        benchmark_ticker="IHSG",
    ))

    assert response.trade_count == 1
    assert response.candidate_observations
    assert response.total_return_pct == 1.0
    assert response.final_equity == Decimal("1010000")
    trade = response.trades[0]
    assert trade.ticker == "BBCA"
    assert trade.exit_reason == "target"
    assert trade.net_return_pct == 5.0
    assert trade.lots == 20
    assert trade.regime is not None
    assert trade.setup_match == "MATCH"
    assert trade.setup_gates
    assert trade.signal_score is not None
    assert trade.signal_strength is not None
    assert trade.signal_breakdown
    assert trade.risk_status is None
    assert trade.trade_setup_action is None
    assert trade.market_context is not None
    trade_dict = trade.to_dict()
    assert trade_dict["foreign_flow_score"] == trade.foreign_flow_score
    assert trade_dict["setup_match"] == "MATCH"
    assert trade_dict["signal_score"] == trade.signal_score
    assert trade_dict["risk_status"] is None
    assert trade_dict["market_context"]["regime"] == trade.regime
    assert "score" not in trade_dict
    assert response.regime_stats
    summary = response.attribution_summary.to_dict()
    assert summary["intent"] == "learning_summary_only_not_entry_logic"
    assert any(
        stat["dimension"] == "signal_strength"
        for stat in summary["group_stats"]
    )
    assert any(
        stat["dimension"] == "candidate_setup_match"
        for stat in summary["candidate_group_stats"]
    )


def test_swing_backtest_can_prioritize_target_when_same_day_hits_stop_and_target():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    candles = [
        _flat_candle(
            "BBCA",
            base + timedelta(days=i),
            Decimal("100") if i % 2 == 0 else Decimal("101"),
        )
        for i in range(25)
    ]
    candles.append(
        _ohlc(
            "BBCA",
            exit_date,
            Decimal("100"),
            Decimal("106"),
            Decimal("94"),
            Decimal("100"),
        )
    )
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
        same_day_exit_priority="target_first",
    ))

    assert response.trade_count == 1
    assert response.trades[0].exit_reason == "target"
    assert response.trades[0].net_return_pct == 5.0


def test_swing_backtest_can_prioritize_stop_when_same_day_hits_stop_and_target():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    candles = [
        _flat_candle(
            "BBCA",
            base + timedelta(days=i),
            Decimal("100") if i % 2 == 0 else Decimal("101"),
        )
        for i in range(25)
    ]
    candles.append(
        _ohlc(
            "BBCA",
            exit_date,
            Decimal("100"),
            Decimal("106"),
            Decimal("94"),
            Decimal("100"),
        )
    )
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
        same_day_exit_priority="stop_first",
    ))

    assert response.trade_count == 1
    assert response.trades[0].exit_reason == "stop"
    assert response.trades[0].net_return_pct == -5.0


def test_swing_backtest_force_exit_period_end():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    exit_date = base + timedelta(days=25)
    candles = [
        _flat_candle(
            "BBCA",
            base + timedelta(days=i),
            Decimal("100") if i % 2 == 0 else Decimal("101"),
        )
        for i in range(25)
    ]
    candles.append(_flat_candle("BBCA", exit_date, Decimal("100")))
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

    assert response.trade_count == 1
    assert response.trades[0].exit_reason == "period_end"
    assert response.trades[0].exit_price == Decimal("100")
