"""
Tests for walk-forward swing backtest.

The backtest must be deterministic, offline, and portfolio-aware.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.assess_risk_use_case import AssessRiskResponse
from src.application.use_case.swing_backtest_use_case import (
    DEFAULT_SWING_COST_BPS,
    SwingBacktestRequest,
    SwingBacktestUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


class MockMarketRepository(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        candles = self.get_candles(ticker)
        if not candles:
            return None
        return candles[0].date, candles[-1].date


class MockBrokerRepository(BrokerDataRepository):
    def __init__(self, summaries: list[BrokerSummary]) -> None:
        self._summaries = summaries

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self._summaries.append(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self._summaries.extend(summaries)

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        for summary in self._summaries:
            if summary.ticker == ticker.upper() and summary.date == target_date:
                return summary
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        rows = [s for s in self._summaries if s.ticker == ticker.upper()]
        if start_date is not None:
            rows = [s for s in rows if s.date >= start_date]
        if end_date is not None:
            rows = [s for s in rows if s.date <= end_date]
        return sorted(rows, key=lambda s: s.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class FakeRiskEngine:
    def __init__(self) -> None:
        self.contexts = []

    def assess_with_context(self, ticker, gate_context, market_context=None):
        self.contexts.append(gate_context)
        assessment = RiskAssessment(
            rationale=("all gates passed",),
            snapshot_date=gate_context.snapshot_date,
            indicators=IndicatorSnapshot(
                date=gate_context.snapshot_date,
                sma=Decimal("100"),
                ema=Decimal("100"),
                rsi=Decimal("50"),
            ),
        )
        return AssessRiskResponse(
            ticker=ticker,
            assessment=assessment,
            sma_period=20,
            ema_period=20,
            rsi_period=14,
        )


class FailingRiskEngine:
    def assess_with_context(self, ticker, gate_context, market_context=None):
        raise ValueError("missing attribution inputs")


def _ohlc(
    ticker: str,
    day: date,
    open_price: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
    )


def _flat_candle(ticker: str, day: date, close: Decimal) -> Candle:
    return _ohlc(ticker, day, close, close, close, close)


def _summary(ticker: str, day: date, foreign_vwap: Decimal) -> BrokerSummary:
    buy_lot = 10_000
    buy_value = foreign_vwap * Decimal(buy_lot * 100)
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=buy_value,
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=buy_lot,
        foreign_sell_lot=0,
        total_value=buy_value * Decimal("2"),
        total_lot=buy_lot * 2,
    )


def _base_candles(ticker: str, base: date) -> list[Candle]:
    candles = [
        _flat_candle(
            ticker,
            base + timedelta(days=i),
            Decimal("100") if i % 2 == 0 else Decimal("101"),
        )
        for i in range(25)
    ]
    candles.append(
        _ohlc(
            ticker,
            base + timedelta(days=25),
            Decimal("100"),
            Decimal("106"),
            Decimal("99"),
            Decimal("105"),
        )
    )
    return candles


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
    use_case = SwingBacktestUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(
            _base_candles("BBCA", base) + benchmark_candles
        ),
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


def test_swing_backtest_records_rejected_candidate_observations():
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
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
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
    use_case = SwingBacktestUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(
            _base_candles("BBCA", base) + benchmark_candles
        ),
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
