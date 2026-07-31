"""
Wiring tests proving production composition roots thread `as_of_date`
through to the risk path (invariant #5).

Component-level tests (test_assess_risk_pit_cutoff.py, etc.) prove the PIT
cutoff behavior of individual use cases in isolation, but they don't prove
that the production callers actually pass `as_of_date` through. These tests
close that gap using SPY doubles that record what they receive, wired to the
real production classes (RiskEngine, SwingBacktestTradeSetupAttributor,
ScreenAssessmentPipeline).

All dates are FIXED. All tests run offline.
"""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.risk_engine import RiskEngine
from src.application.services.screen_assessment_pipeline import ScreenAssessmentPipeline
from src.application.services.screen_policy import ScreenPolicy
from src.application.services.swing_backtest_trade_setup_attributor import (
    SwingBacktestTradeSetupAttributor,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.signal_assessment import (
    ACCUMULATION_DISCOVERY_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)

_START = date(2026, 1, 1)
_TICKER = "BBCA"


def _liquid_candle(day: date) -> Candle:
    """close=10_000, volume=1_000_000 -> tx=10B IDR/day (2x the 5B floor)."""
    return Candle(
        ticker=_TICKER,
        date=day,
        open=Decimal("10000"),
        high=Decimal("10000"),
        low=Decimal("10000"),
        close=Decimal("10000"),
        volume=1_000_000,
    )


def _liquid_series(count: int, start: date = _START) -> list[Candle]:
    return [_liquid_candle(start + timedelta(days=i)) for i in range(count)]


class RecordingRepo(MarketDataRepository):
    """Local copy of the RecordingRepo from test_assess_risk_pit_cutoff.py —
    records every (start_date, end_date) passed to get_candles()."""

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles
        self.calls: list[tuple[date | None, date | None]] = []

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        self.calls.append((start_date, end_date))
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if not rows:
            return None
        rows = sorted(rows, key=lambda c: c.date)
        return rows[0].date, rows[-1].date


def test_assess_with_context_threads_cutoff():
    """RiskEngine.assess_with_context(..., as_of_date=D) must bound every
    repository.get_candles() call it triggers by D — proving the engine
    (not just the evaluator it wraps) threads the cutoff through."""
    cutoff = _START + timedelta(days=150)
    candles = _liquid_series(260)
    repo = RecordingRepo(candles)

    engine = RiskEngine(
        repository=repo,
        registry=IndicatorRegistry(),
        structural_gates=[LiquidityGate()],
        execution_gates=[],
    )

    gate_context = GateContext(ticker=_TICKER, snapshot_date=cutoff)
    engine.assess_with_context(_TICKER, gate_context, as_of_date=cutoff)

    assert repo.calls, "expected at least one get_candles() call to be recorded"
    assert all(end_date is not None and end_date <= cutoff for _, end_date in repo.calls)


class _SpyRiskEngine:
    """Records the as_of_date it was called with; returns a fixed response."""

    def __init__(self, response) -> None:
        self._response = response
        self.recorded_as_of_date: date | None = None

    def assess_with_context(self, ticker, gate_context, market_context=None, as_of_date=None):
        self.recorded_as_of_date = as_of_date
        return self._response


def _minimal_candidate(signal_assessment) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=_TICKER,
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("10000000"),
        consecutive_streak=3,
        foreign_vwap=None,
        current_price=Decimal("5000"),
        vwap_discount_pct=None,
        rsi=45.0,
        trend="UP",
        accum_score=75.0,
        top_brokers=None,
        institutional_flag=False,
        signal_assessment=signal_assessment,
    )


def test_swing_attributor_passes_signal_date():
    """SwingBacktestTradeSetupAttributor.assess() must pass signal_date as
    as_of_date to RiskEngine.assess_with_context()."""
    signal_date = _START + timedelta(days=150)

    signal_response = AssessSignalResponse(
        ticker=_TICKER,
        assessment=SignalAssessment(
            identity=ACCUMULATION_DISCOVERY_IDENTITY,
            ticker=_TICKER,
            score=76,
            strength=SignalStrength.STRONG,
            entry_quality=EntryQuality.ENTER,
            breakdown=(("foreign_flow_quality", 80.0),),
            rationale=("signal supportive",),
            snapshot_date=signal_date,
            signal_authority_coverage=None,
        ),
    )
    risk_response = _dummy_risk_response(signal_date)

    spy = _SpyRiskEngine(risk_response)
    attributor = SwingBacktestTradeSetupAttributor(risk_engine=spy)
    candidate = _minimal_candidate(signal_response)

    attributor.assess(candidate, signal_date, None)

    assert spy.recorded_as_of_date == signal_date


def _dummy_risk_response(snapshot_date: date):
    from src.application.dto.assess_risk import AssessRiskResponse

    return AssessRiskResponse(
        ticker=_TICKER,
        assessment=RiskAssessment(
            rationale=("no gate fired",),
            snapshot_date=snapshot_date,
            indicators=IndicatorSnapshot(
                date=snapshot_date,
                sma=Decimal("5000"),
                ema=Decimal("5000"),
                rsi=Decimal("50"),
            ),
            gate_triggered=None,
            gate_is_structural=None,
            gate_confidence=None,
        ),
        sma_period=20,
        ema_period=20,
        rsi_period=14,
    )


class _StubRiskInputsBuilder:
    """Always returns a fixed, pre-built GateContext (pre-built path)."""

    def __init__(self, gate_context: GateContext) -> None:
        self._gate_context = gate_context

    def build(self, candidate: object, *, as_of_date: date) -> GateContext | None:
        return self._gate_context


class _SpyRiskUseCase:
    """Records the AssessRiskRequest.as_of_date it was called with."""

    def __init__(self, response) -> None:
        self._response = response
        self.recorded_as_of_date: date | None = None

    def execute(self, request):
        self.recorded_as_of_date = request.as_of_date
        return self._response


def test_screen_pipeline_passes_cutoff_on_prebuilt_path():
    """ScreenAssessmentPipeline.assess_risk(..., as_of_date=D) must pass D
    through on AssessRiskRequest.as_of_date when the RiskInputsBuilder
    returns a pre-built GateContext (pre-built path)."""
    as_of_date = _START + timedelta(days=150)
    gate_context = GateContext(ticker=_TICKER, snapshot_date=as_of_date)
    risk_response = _dummy_risk_response(as_of_date)

    spy_use_case = _SpyRiskUseCase(risk_response)
    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.accumulation(),
        risk_use_case=spy_use_case,
        risk_inputs_builder=_StubRiskInputsBuilder(gate_context),
    )

    candidate = SimpleNamespace(ticker=_TICKER)
    pipeline.assess_risk(candidate, as_of_date=as_of_date)

    assert spy_use_case.recorded_as_of_date == as_of_date
