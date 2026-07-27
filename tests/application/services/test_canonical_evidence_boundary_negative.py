"""Negative tests required by the CANONICAL-EVIDENCE-BOUNDARY repair task
(ADR-041). Covers items not already exercised by
`tests/domain/value_objects/test_canonical_signal_evidence_input.py` or
`tests/application/services/test_accumulation_candidate_evaluator.py`:

1. Swing performs no second broker query after candidate evaluation.
2. The exact broker row object identities from evaluation reach BuiltFlowEvidence.
3. A future broker summary raises ValueError.
4. A future broker daily-flow row raises ValueError.
5. A future ticker candle raises ValueError.
6. A future IHSG candle raises ValueError.
8. Loose evidence cannot be supplied to SignalEngine.
12. Contract ValueError escapes instead of becoming a warning.
13. Screen and swing produce equivalent canonical signal-evidence input at
    their real application boundaries. This executes
    `AccumulationCandidateSignalAssessor.assess()` (screen),
    `SwingAnalysisEvidenceBuilder.build()` (swing evidence), and
    `SwingAnalysisDecisionComposer.recompose_after_evidence()` (swing
    canonical/scoring) — not the same builder invoked twice in the test
    body. It captures the complete `CanonicalSignalEvidenceInput` each real
    boundary hands to its own `SignalEngine.evaluate_accumulation_discovery()` call
    and asserts the two are equal, including availability, so a divergence
    in effective session, source-availability wiring, or canonical
    assembly between the two workflows would be caught here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationCandidateEvaluationResult,
    AccumulationScreenRequest,
)
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.built_evidence import BuiltSetupEvidence
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.accumulation_candidate_signal_assessor import (
    AccumulationCandidateSignalAssessor,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)
from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.signal_engine import SignalEngine
from src.application.services.swing_analysis_decision_composer import (
    SwingAnalysisDecisionComposer,
)
from src.application.services.swing_analysis_evidence_builder import (
    SwingAnalysisEvidenceBuilder,
)
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.application.use_case.score_accum_use_case import ScoreAccumUseCase
from src.domain.entities.candle import Candle
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from src.domain.value_objects.canonical_signal_evidence_input import (
    CandleRowIdentity,
    CanonicalSignalEvidenceInput,
    FlowEvidenceGroupInput,
    SetupProvenance,
)
from src.domain.value_objects.factor_evidence import Freshness
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalContext,
    SignalStrength,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    _daily_flow as _make_daily_flow,
)
from tests.application.use_case.accumulation_screen_fixtures import _summary as _make_summary

TICKER = "BBCA"
SNAP = date(2026, 7, 17)


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker=TICKER,
        window_days=7,
        net_buy_days=4,
        total_days=5,
        net_buy_ratio=0.8,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=50.0,
        trend="UP",
        accum_score=50.0,
        top_brokers=None,
        institutional_flag=False,
        latest_candle_date=SNAP,
        latest_broker_date=SNAP,
        latest_broker_daily_flow_date=SNAP,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _summary(day: date):
    return _make_summary(TICKER, day, Decimal("1000"))


def _daily_flow(day: date, broker_code: str = "AK"):
    return _make_daily_flow(TICKER, day, broker_code, 100)


def _no_excess_return() -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=5,
        ticker_return_pct=None,
        benchmark_return_pct=None,
        excess_return_pct=None,
        window_start=None,
        window_end=None,
        common_session_count=0,
        status=BenchmarkExcessReturnStatus.UNAVAILABLE,
        unavailable_reason="test",
    )


# --- 3/4: AccumulationCandidateEvaluationResult rejects future consumed rows ---


class TestEvaluationResultRejectsFutureRows:
    def test_future_broker_summary_row_raises(self):
        with pytest.raises(ValueError, match="after analysis_date"):
            AccumulationCandidateEvaluationResult(
                candidate=_candidate(latest_broker_date=SNAP + timedelta(days=1)),
                consumed_candles=(),
                consumed_broker_summaries=(_summary(SNAP + timedelta(days=1)),),
                consumed_broker_daily_flows=(),
                analysis_date=SNAP,
            )

    def test_future_broker_daily_flow_row_raises(self):
        with pytest.raises(ValueError, match="after analysis_date"):
            AccumulationCandidateEvaluationResult(
                candidate=_candidate(latest_broker_daily_flow_date=SNAP + timedelta(days=1)),
                consumed_candles=(),
                consumed_broker_summaries=(),
                consumed_broker_daily_flows=(_daily_flow(SNAP + timedelta(days=1)),),
                analysis_date=SNAP,
            )

    def test_future_candle_row_raises(self):
        candle = Candle(
            ticker=TICKER,
            date=SNAP + timedelta(days=1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000,
        )
        with pytest.raises(ValueError, match="after analysis_date"):
            AccumulationCandidateEvaluationResult(
                candidate=_candidate(latest_candle_date=SNAP + timedelta(days=1)),
                consumed_candles=(candle,),
                consumed_broker_summaries=(),
                consumed_broker_daily_flows=(),
                analysis_date=SNAP,
            )


# --- 5/6: BuiltSetupEvidence rejects future ticker/benchmark candles ---


def _setup_evidence() -> SetupEvidence:
    return SetupEvidence(
        ticker=TICKER,
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match="MATCH",
        match_strength=100.0,
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.2,
        vwap_discount_pct=1.5,
        vwap_pct=1.0,
        benchmark_excess_return_5_session=_no_excess_return(),
        benchmark_excess_return_20_session=_no_excess_return(),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="test",
    )


class TestBuiltSetupEvidenceRejectsFutureRows:
    def test_future_ticker_candle_raises(self):
        provenance = SetupProvenance(
            ticker=TICKER,
            candle_rows=(
                CandleRowIdentity(ticker=TICKER, date=SNAP + timedelta(days=1), source="test"),
            ),
        )
        with pytest.raises(ValueError, match="after evidence.snapshot_date"):
            BuiltSetupEvidence(evidence=_setup_evidence(), provenance=provenance)

    def test_future_ihsg_candle_raises(self):
        provenance = SetupProvenance(
            ticker=TICKER,
            candle_rows=(CandleRowIdentity(ticker=TICKER, date=SNAP, source="test"),),
            benchmark_candle_rows=(
                CandleRowIdentity(
                    ticker=CANONICAL_BENCHMARK_TICKER, date=SNAP + timedelta(days=1), source="test"
                ),
            ),
        )
        with pytest.raises(ValueError, match="after evidence.snapshot_date"):
            BuiltSetupEvidence(evidence=_setup_evidence(), provenance=provenance)


# --- 1/2: swing does not re-query broker repo; exact rows reach BuiltFlowEvidence ---


class _RaisingBrokerRepository:
    """Any broker query on this repository is a contract violation for
    SwingAnalysisEvidenceBuilder — it must only use
    AccumulationCandidateEvaluationResult.consumed_broker_summaries/
    consumed_broker_daily_flows, never re-query."""

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        raise AssertionError("swing must not re-query broker_summaries")

    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        raise AssertionError("swing must not re-query broker_daily_flows")

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        raise AssertionError("swing must not re-query foreign_flow_points")


class _MarketRepository:
    def get_candles(self, ticker, start_date=None, end_date=None):
        return []

    def get_candle_source(self, ticker, on_date):
        return None


def _builder(broker_repository) -> SwingAnalysisEvidenceBuilder:
    return SwingAnalysisEvidenceBuilder(
        market_repository=_MarketRepository(),
        broker_repository=broker_repository,
        registry=None,
        rules_loader=SimpleNamespace(),
        flow_confirmation_builder=FlowConfirmationEvidenceBuilder(),
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
    )


def test_swing_evidence_builder_never_queries_broker_repository():
    summary_row = _summary(SNAP)
    daily_flow_row = _daily_flow(SNAP)
    evaluation_result = AccumulationCandidateEvaluationResult(
        candidate=_candidate(latest_candle_date=None),
        consumed_candles=(),
        consumed_broker_summaries=(summary_row,),
        consumed_broker_daily_flows=(daily_flow_row,),
        analysis_date=SNAP,
    )
    builder = _builder(_RaisingBrokerRepository())

    result = builder.build(
        ticker=TICKER,
        snapshot_date=SNAP,
        benchmark="IHSG",
        candles=[],
        accumulation_evaluation=evaluation_result,
        setup_eval=None,
        setup_name=None,
        strategy_name=None,
        swing_config=None,
    )

    # No AssertionError was raised -> broker repository was never queried.
    assert result.built_flow_evidence is not None
    provenance = result.built_flow_evidence.provenance
    assert len(provenance.broker_summary_rows) == 1
    assert provenance.broker_summary_rows[0].date == summary_row.date
    assert provenance.broker_summary_rows[0].ticker == summary_row.ticker
    assert len(provenance.broker_daily_flow_rows) == 1
    assert provenance.broker_daily_flow_rows[0].date == daily_flow_row.date
    assert provenance.broker_daily_flow_rows[0].broker_code == daily_flow_row.broker_code


# --- 8: loose evidence cannot be supplied to SignalEngine ---


def test_signal_engine_rejects_loose_setup_evidence_kwarg():
    engine = SignalEngine()
    ctx = SignalContext(ticker=TICKER, snapshot_date=SNAP)
    with pytest.raises(TypeError):
        engine.evaluate_accumulation_discovery(
            TICKER,
            ctx,
            setup_evidence=_setup_evidence(),  # type: ignore[call-arg]
        )


def test_signal_engine_rejects_loose_flow_confirmation_evidence_kwarg():
    engine = SignalEngine()
    ctx = SignalContext(ticker=TICKER, snapshot_date=SNAP)
    with pytest.raises(TypeError):
        engine.evaluate_accumulation_discovery(
            TICKER,
            ctx,
            flow_confirmation_evidence=None,  # type: ignore[call-arg]
        )


# --- 12: contract ValueError escapes instead of becoming a warning ---


def test_flow_confirmation_evidence_builder_ticker_mismatch_escapes_as_valueerror():
    # A broker row from a different ticker than the candidate is a contract
    # violation (FlowProvenance ticker mismatch) — it must raise, not be
    # caught anywhere and downgraded to a warning.
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate()
    foreign_row = _summary(SNAP)
    object.__setattr__(foreign_row, "ticker", "ASII")

    with pytest.raises(ValueError, match="ticker mismatch"):
        builder.build(
            candidate,
            analysis_date=SNAP,
            consumed_broker_summaries=(foreign_row,),
            consumed_broker_daily_flows=(),
        )


def test_swing_evidence_builder_propagates_duplicate_row_violation_not_a_warning():
    # SwingAnalysisEvidenceBuilder's flow-evidence try/except must re-raise a
    # ValueError from a provenance contract violation — here, a duplicate
    # consumed broker-summary row (which AccumulationCandidateEvaluationResult
    # itself does not check for, but FlowProvenance does) — rather than
    # appending "Flow confirmation evidence unavailable: ..." to warnings.
    duplicated_row = _summary(SNAP)
    evaluation_result = AccumulationCandidateEvaluationResult(
        candidate=_candidate(latest_candle_date=None, latest_broker_daily_flow_date=None),
        consumed_candles=(),
        consumed_broker_summaries=(duplicated_row, duplicated_row),
        consumed_broker_daily_flows=(),
        analysis_date=SNAP,
    )
    builder = _builder(_RaisingBrokerRepository())

    with pytest.raises(ValueError, match="duplicate"):
        builder.build(
            ticker=TICKER,
            snapshot_date=SNAP,
            benchmark="IHSG",
            candles=[],
            accumulation_evaluation=evaluation_result,
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )


# --- 13: screen and swing execute equivalent canonical evidence input ---


class _CanonicalInputRecordingSignalEngine:
    """Strict recording fake — never a MagicMock. Records the exact kwargs
    each real boundary passes to its contextual policy, including
    `canonical_evidence`, so the test can compare what screen and swing
    actually handed to SignalEngine rather than re-deriving it."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def foreign_flow_quality_from_accum_score(self, score):
        return "MODERATE"

    def bandar_max_range(self, num_optional):
        return 12.0

    def evaluate_accumulation_discovery(self, ticker, signal_ctx, **kwargs):
        return self._record(ticker, signal_ctx, kwargs)

    def evaluate_swing_trade_setup(self, ticker, signal_ctx, **kwargs):
        return self._record(ticker, signal_ctx, kwargs)

    def _record(self, ticker, signal_ctx, kwargs):
        self.calls.append(
            {
                "ticker": ticker,
                "signal_ctx": signal_ctx,
                "kwargs": kwargs,
            }
        )
        return _signal_response()


class _RecordingCandidateEvidenceBuilder:
    """Strict fake for the setup-phase collaborator. Setup phase is outside
    this flow-only parity test; it performs no repository access."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def resolve_preliminary_setup_family_result(self, candidate):
        from src.application.services.primary_setup_family_resolver import (
            PrimarySetupFamilyResult,
        )

        return PrimarySetupFamilyResult(
            matched_setup_families=(),
            primary_setup_family=None,
            setup_family_source="fallback_unknown",
        )

    def detect_candidate_setup_phase(self, candidate, flow_evidence, as_of_date, setup_family=None):
        self.calls.append(
            {
                "candidate": candidate,
                "flow_evidence": flow_evidence,
                "as_of_date": as_of_date,
                "setup_family": setup_family,
            }
        )
        return None


class _RecordingFlowConfirmationEvidenceBuilder(FlowConfirmationEvidenceBuilder):
    """Records every `build()` call's exact arguments so the test can prove
    both boundaries pass the identical consumed-row tuple objects through
    to the same builder, rather than inferring transport from the absence
    of a broker-repository AssertionError (which does not, by itself, rule
    out other unrelated repository reads)."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    def build(
        self,
        candidate,
        *,
        consumed_broker_summaries,
        consumed_broker_daily_flows,
        group_cap=0.80,
        analysis_date=None,
    ):
        self.calls.append(
            {
                "candidate": candidate,
                "consumed_broker_summaries": consumed_broker_summaries,
                "consumed_broker_daily_flows": consumed_broker_daily_flows,
                "analysis_date": analysis_date,
            }
        )
        return super().build(
            candidate,
            consumed_broker_summaries=consumed_broker_summaries,
            consumed_broker_daily_flows=consumed_broker_daily_flows,
            group_cap=group_cap,
            analysis_date=analysis_date,
        )


class _EmptyBrokerRepository:
    """Non-raising broker repository for the parity fixture. Institutional
    evidence reads (unrelated to flow provenance transport) are legitimate
    here; only flow-evidence lineage is asserted via the recording flow
    builder above."""

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        return []

    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        return []

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        return []


class _RecordingRiskTradeSetupComposer:
    """Strict fake — records `recompose_after_signal_rescore` kwargs and
    returns the fallback values unchanged, since this test only asserts on
    the canonical signal-evidence input, not on trade-setup recomposition."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def recompose_after_signal_rescore(self, **kwargs):
        self.calls.append(kwargs)
        return (
            kwargs["fallback_trade_setup"],
            kwargs["fallback_market_context_signal_preview"],
            kwargs["fallback_market_context_trade_setup_preview"],
            [],
        )


def _signal_response(score: int = 72) -> AssessSignalResponse:
    assessment = SignalAssessment(
        identity=SWING_TRADE_SETUP_IDENTITY,
        ticker=TICKER,
        score=score,
        strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("setup", 60.0), ("flow", 40.0)),
        rationale=("test rationale",),
        snapshot_date=SNAP,
        signal_authority_coverage=None,
    )
    return AssessSignalResponse(ticker=TICKER, assessment=assessment)


def _swing_request_for(today: date, ticker: str) -> swing_analysis_dto.SwingAnalysisWorkflowRequest:
    return swing_analysis_dto.SwingAnalysisWorkflowRequest(
        ticker=ticker,
        today=today,
        strategy_name=None,
        setup_name=None,
        window=200,
        flow_window=20,
        capital=None,
        risk_pct=1.0,
        entry_price=None,
        atr_mult=2.0,
        rr=2.0,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
        sentiment_verbose=False,
        auto_refresh=False,
        force_refresh=False,
        with_market_context=False,
        regime_universe="lq45",
        benchmark="IHSG",
        db_path=Path("/tmp/does-not-exist.db"),
        with_technical_gate=False,
    )


@dataclass
class _ParityBoundaryResult:
    candidate: AccumulationCandidate
    summaries: tuple
    daily_flows: tuple
    effective_session: EffectiveMarketSession
    source_availability_use_case: AssessSourceAvailabilityUseCase
    screen_result: object
    screen_signal_engine: _CanonicalInputRecordingSignalEngine
    screen_canonical: CanonicalSignalEvidenceInput
    recording_candidate_evidence_builder: _RecordingCandidateEvidenceBuilder
    flow_builder: _RecordingFlowConfirmationEvidenceBuilder
    swing_evidence_result: object
    swing_signal_engine: _CanonicalInputRecordingSignalEngine
    swing_canonical: CanonicalSignalEvidenceInput
    risk_composer: _RecordingRiskTradeSetupComposer


@pytest.fixture(scope="module")
def parity_boundaries() -> _ParityBoundaryResult:
    """Executes the real screen and swing application boundaries exactly
    once (shared by both parity tests below via module-scoped caching), so
    the negative sensitivity test does not need to re-run either boundary
    to prove the assertions can detect divergence."""
    candidate = _candidate(
        latest_candle_date=None,
        latest_broker_date=SNAP,
        latest_broker_daily_flow_date=SNAP,
    )
    summaries = (
        _summary(SNAP - timedelta(days=1)),
        _summary(SNAP),
    )
    daily_flows = (_daily_flow(SNAP, "AK"),)

    decision_at = datetime(2026, 7, 17, 16, 15, tzinfo=IDX_TIMEZONE)
    effective_session = EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=SNAP,
        analysis_as_of=SNAP,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )
    calendar = KnownTradingSessionCalendar(
        sessions=(SNAP - timedelta(days=1), SNAP),
        coverage_start=SNAP - timedelta(days=1),
        coverage_end=SNAP,
    )
    source_availability_use_case = AssessSourceAvailabilityUseCase(calendar=calendar)

    # Same policy for both call sites — never independently instantiated.
    # Recording subclass proves exact-object transport (lineage), not just
    # equal-valued outputs.
    flow_builder = _RecordingFlowConfirmationEvidenceBuilder()

    # --- Screen boundary: AccumulationCandidateSignalAssessor.assess() ---
    screen_signal_engine = _CanonicalInputRecordingSignalEngine()
    recording_candidate_evidence_builder = _RecordingCandidateEvidenceBuilder()
    assessor = AccumulationCandidateSignalAssessor(
        signal_engine=screen_signal_engine,
        flow_confirmation_builder=flow_builder,
        candidate_evidence_builder=recording_candidate_evidence_builder,
        accum_score_uc=ScoreAccumUseCase(),
    )
    request = AccumulationScreenRequest(
        tickers=[TICKER],
        window_days=7,
        min_net_buy_days=1,
        min_accum_score_enabled=False,
        min_signal_score_enabled=False,
    )
    screen_result = assessor.assess(
        candidate,
        request=request,
        as_of_date=SNAP,
        consumed_broker_summaries=summaries,
        consumed_broker_daily_flows=daily_flows,
        effective_session=effective_session,
        source_availability_use_case=source_availability_use_case,
    )
    screen_canonical = screen_signal_engine.calls[0]["kwargs"]["canonical_evidence"]

    # --- Swing evidence boundary: SwingAnalysisEvidenceBuilder.build() ---
    # The exact candidate returned by screen and the exact shared row
    # tuples — never a second candidate, never reconstructed broker rows.
    evaluation_result = AccumulationCandidateEvaluationResult(
        candidate=screen_result.candidate,
        consumed_candles=(),
        consumed_broker_summaries=summaries,
        consumed_broker_daily_flows=daily_flows,
        analysis_date=SNAP,
    )
    swing_evidence_builder = SwingAnalysisEvidenceBuilder(
        market_repository=_MarketRepository(),
        broker_repository=_EmptyBrokerRepository(),
        registry=None,
        rules_loader=SimpleNamespace(),
        flow_confirmation_builder=flow_builder,
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
    )
    swing_evidence_result = swing_evidence_builder.build(
        ticker=TICKER,
        snapshot_date=SNAP,
        benchmark="IHSG",
        candles=[],
        accumulation_evaluation=evaluation_result,
        setup_eval=None,
        setup_name=None,
        strategy_name=None,
        swing_config=None,
    )

    # --- Swing canonical/scoring boundary: recompose_after_evidence() ---
    execution_context = SignalEvidenceExecutionContext(
        effective_session=effective_session,
        source_availability_use_case=source_availability_use_case,
    )
    state = SwingAnalysisWorkflowState()
    state.accumulation_evaluation = evaluation_result
    state.signal_evidence_execution_context = execution_context
    state.built_setup_evidence = None
    state.built_flow_evidence = swing_evidence_result.built_flow_evidence
    state.signal_assessment = _signal_response()
    state.risk_response = None
    state.trade_setup = None
    state.market_context_signal_preview = None
    state.market_context_risk_preview = None
    state.market_context_trade_setup_preview = None
    state.market_regime = None
    state.verdict = swing_analysis_dto.SwingVerdict(
        trade_setup=None,
        signal_assessment=state.signal_assessment,
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=swing_analysis_dto.SignalAssessmentAvailability(
            status=swing_analysis_dto.SignalAssessmentStatus.AVAILABLE
        ),
    )

    swing_signal_engine = _CanonicalInputRecordingSignalEngine()
    risk_composer = _RecordingRiskTradeSetupComposer()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=risk_composer,
        signal_engine=swing_signal_engine,
    )
    composer.recompose_after_evidence(_swing_request_for(SNAP, TICKER), state)
    swing_canonical = swing_signal_engine.calls[0]["kwargs"]["canonical_evidence"]

    return _ParityBoundaryResult(
        candidate=candidate,
        summaries=summaries,
        daily_flows=daily_flows,
        effective_session=effective_session,
        source_availability_use_case=source_availability_use_case,
        screen_result=screen_result,
        screen_signal_engine=screen_signal_engine,
        screen_canonical=screen_canonical,
        recording_candidate_evidence_builder=recording_candidate_evidence_builder,
        flow_builder=flow_builder,
        swing_evidence_result=swing_evidence_result,
        swing_signal_engine=swing_signal_engine,
        swing_canonical=swing_canonical,
        risk_composer=risk_composer,
    )


def test_screen_and_swing_boundaries_pass_equivalent_canonical_flow_input(
    parity_boundaries: _ParityBoundaryResult,
) -> None:
    b = parity_boundaries

    assert b.screen_canonical is not None
    assert b.screen_canonical.setup is None
    assert b.screen_canonical.flow is not None
    assert b.screen_result.candidate is b.candidate

    assert b.swing_evidence_result.built_setup_evidence is None
    assert b.swing_evidence_result.built_flow_evidence is not None

    assert b.swing_canonical is not None
    assert b.swing_canonical.setup is None
    assert b.swing_canonical.flow is not None

    # Complete typed objects, then each layer explicitly for diagnosability.
    assert b.screen_canonical == b.swing_canonical
    assert b.screen_canonical.flow.evidence == b.swing_canonical.flow.evidence
    assert b.screen_canonical.flow.provenance == b.swing_canonical.flow.provenance
    assert b.screen_canonical.flow.availability == b.swing_canonical.flow.availability

    assert tuple(
        (row.ticker, row.date, row.source)
        for row in b.screen_canonical.flow.provenance.broker_summary_rows
    ) == tuple(
        (row.ticker, row.date, row.source)
        for row in b.swing_canonical.flow.provenance.broker_summary_rows
    )
    assert tuple(
        (row.ticker, row.date, row.broker_code, row.source)
        for row in b.screen_canonical.flow.provenance.broker_daily_flow_rows
    ) == tuple(
        (row.ticker, row.date, row.broker_code, row.source)
        for row in b.swing_canonical.flow.provenance.broker_daily_flow_rows
    )

    for assessment in b.screen_canonical.flow.availability.assessments:
        assert assessment.decision_at == b.effective_session.decision_at
    for assessment in b.swing_canonical.flow.availability.assessments:
        assert assessment.decision_at == b.effective_session.decision_at

    expected_source_families = ("broker_summaries", "broker_daily_flow")
    assert (
        tuple(a.source_family for a in b.screen_canonical.flow.availability.assessments)
        == expected_source_families
    )
    assert (
        tuple(a.source_family for a in b.swing_canonical.flow.availability.assessments)
        == expected_source_families
    )

    assert len(b.screen_signal_engine.calls) == 1
    assert len(b.swing_signal_engine.calls) == 1
    assert len(b.recording_candidate_evidence_builder.calls) == 1
    assert len(b.risk_composer.calls) == 1

    # Lineage: both boundaries pass FlowConfirmationEvidenceBuilder.build()
    # the *same* consumed-row tuple objects and the *same* candidate object
    # — not merely value-equal reconstructions. An absence of a broker-
    # repository AssertionError does not, by itself, prove this; the
    # institutional-evidence path may read the broker repository directly
    # without going through the exact-row consumed tuples.
    assert len(b.flow_builder.calls) == 2
    screen_flow_call, swing_flow_call = b.flow_builder.calls
    assert screen_flow_call["consumed_broker_summaries"] is b.summaries
    assert swing_flow_call["consumed_broker_summaries"] is b.summaries
    assert screen_flow_call["consumed_broker_daily_flows"] is b.daily_flows
    assert swing_flow_call["consumed_broker_daily_flows"] is b.daily_flows
    assert screen_flow_call["candidate"] is b.candidate
    assert swing_flow_call["candidate"] is b.candidate

    assert b.swing_evidence_result.warnings == ()


def test_parity_fixture_detects_different_effective_sessions(
    parity_boundaries: _ParityBoundaryResult,
) -> None:
    # Sensitivity counterexample: does not re-run either full boundary.
    # Reuses the already-produced swing flow evidence/provenance and only
    # re-derives availability under a different decision_at, proving the
    # parity assertions above would have caught a session divergence.
    b = parity_boundaries
    altered_session = replace(
        b.effective_session, decision_at=b.effective_session.decision_at + timedelta(hours=1)
    )
    altered_flow_availability = EvidenceSourceAvailabilityAssembler(
        b.source_availability_use_case
    ).assess_flow(
        effective_session=altered_session,
        provenance=b.swing_canonical.flow.provenance,
    )
    altered_swing_canonical = CanonicalSignalEvidenceInput(
        setup=None,
        flow=FlowEvidenceGroupInput(
            evidence=b.swing_canonical.flow.evidence,
            provenance=b.swing_canonical.flow.provenance,
            availability=altered_flow_availability,
        ),
    )

    assert b.screen_canonical.flow.evidence == altered_swing_canonical.flow.evidence
    assert b.screen_canonical.flow.provenance == altered_swing_canonical.flow.provenance
    assert b.screen_canonical.flow.availability != altered_swing_canonical.flow.availability
    assert b.screen_canonical != altered_swing_canonical
