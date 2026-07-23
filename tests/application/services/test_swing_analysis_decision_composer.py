"""Tests for SwingAnalysisDecisionComposer's canonical evidence construction
(ADR-041 CANONICAL-EVIDENCE-BOUNDARY).

Proves the composer resolves availability once, pre-score, from exact
provenance, binds it into CanonicalSignalEvidenceInput, gates each group on
its evidence actually having been built this run, and never performs a
separate post-score availability assembly/attachment.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.built_evidence import BuiltFlowEvidence, BuiltSetupEvidence
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.swing_analysis_decision_composer import (
    SwingAnalysisDecisionComposer,
)
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.canonical_signal_evidence_input import (
    BrokerDailyFlowRowIdentity,
    BrokerSummaryRowIdentity,
    CandleRowIdentity,
    FlowProvenance,
    SetupProvenance,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.source_availability import SourceAvailabilityStatus

TICKER = "BBCA"
SNAP = date(2026, 7, 17)


def _request():
    from pathlib import Path

    return swing_analysis_dto.SwingAnalysisWorkflowRequest(
        ticker=TICKER,
        today=SNAP,
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
        benchmark="COMPOSITE",
        db_path=Path("/tmp/does-not-exist.db"),
    )


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
        unavailable_reason="test fixture",
    )


def _built_setup_evidence() -> BuiltSetupEvidence:
    evidence = SetupEvidence(
        ticker=TICKER,
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match="MATCH",
        match_strength=100.0,
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        benchmark_excess_return_5_session=_no_excess_return(),
        benchmark_excess_return_20_session=_no_excess_return(),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="test",
    )
    provenance = SetupProvenance(
        ticker=TICKER,
        candle_rows=(CandleRowIdentity(ticker=TICKER, date=SNAP, source="test"),),
    )
    return BuiltSetupEvidence(evidence=evidence, provenance=provenance)


def _built_flow_evidence(has_bandar_contributor: bool = False) -> BuiltFlowEvidence:
    signal = FlowSubSignal(
        key="cons", score=40.0, weight=40.0, direction=Direction.BULLISH, freshness=Freshness.FRESH
    )
    evidence = FlowConfirmationEvidence(
        ticker=TICKER,
        snapshot_date=SNAP,
        flow_signals=(signal,),
        flow_score_ex_bb=40.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.5,
        capped_strength=0.5,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )
    provenance = FlowProvenance(
        ticker=TICKER,
        broker_summary_rows=(BrokerSummaryRowIdentity(ticker=TICKER, date=SNAP, source="test"),),
        broker_daily_flow_rows=(
            BrokerDailyFlowRowIdentity(ticker=TICKER, date=SNAP, broker_code="AK", source="test"),
        ),
        has_bandar_contributor=has_bandar_contributor,
    )
    return BuiltFlowEvidence(evidence=evidence, provenance=provenance)


def _source_availability_use_case() -> AssessSourceAvailabilityUseCase:
    calendar = KnownTradingSessionCalendar(
        sessions=(SNAP,), coverage_start=SNAP, coverage_end=SNAP
    )
    return AssessSourceAvailabilityUseCase(calendar=calendar)


def _effective_session() -> EffectiveMarketSession:
    decision_at = datetime(SNAP.year, SNAP.month, SNAP.day, 20, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=SNAP,
        analysis_as_of=SNAP,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _signal_response(score: int = 72) -> AssessSignalResponse:
    assessment = SignalAssessment(
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


class _RecordingSignalEngine:
    """Captures the canonical_evidence passed to evaluate_with_context."""

    def __init__(self, response_score: int = 91) -> None:
        self.calls: list[dict] = []
        self._response_score = response_score

    def foreign_flow_quality_from_accum_score(self, score):
        return None

    def bandar_max_range(self, num_optional):
        return 6

    def evaluate_with_context(self, ticker, signal_ctx, **kwargs):
        self.calls.append(kwargs)
        resp = _signal_response(score=self._response_score)
        if kwargs.get("canonical_evidence") is not None:
            from src.domain.value_objects.evidence_source_availability import AvailabilityEnforcementMode
            resp.availability_enforcement = AvailabilityEnforcementMode.SHADOW
        return resp


class _RecordingRiskTradeSetupComposer:
    def recompose_after_signal_rescore(self, **kwargs):
        return ("SENTINEL_TRADE_SETUP", kwargs["signal_assessment"], None, [])


def _state(
    *,
    built_setup_evidence: BuiltSetupEvidence | None,
    built_flow_evidence: BuiltFlowEvidence | None,
    source_availability_use_case: AssessSourceAvailabilityUseCase | None,
) -> SwingAnalysisWorkflowState:
    candidate = SimpleNamespace(
        bandar_detector=None,
        seasonal_edge=None,
        analyst_consensus=None,
        forward_estimates=None,
        current_price=None,
        accum_score=0.0,
        insider_net_buy_ratio=None,
    )
    state = SwingAnalysisWorkflowState()
    state.accumulation_evaluation = SimpleNamespace(candidate=candidate)
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    state.signal_evidence_execution_context = SignalEvidenceExecutionContext(
        effective_session=_effective_session(),
        source_availability_use_case=source_availability_use_case,
    )
    state.candles = [SimpleNamespace(date=SNAP)]
    state.built_setup_evidence = built_setup_evidence
    state.built_flow_evidence = built_flow_evidence
    state.evidence = swing_analysis_dto.SwingEvidence(
        accumulation_candidate=candidate,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        regime_label=None,
        setup_evidence=built_setup_evidence.evidence if built_setup_evidence else None,
        flow_confirmation_evidence=built_flow_evidence.evidence if built_flow_evidence else None,
    )
    state.signal_assessment = _signal_response(score=50)
    state.trade_setup = None
    state.market_context_signal_preview = None
    state.market_context_trade_setup_preview = None
    state.risk_response = None
    state.verdict = swing_analysis_dto.SwingVerdict(
        trade_setup=None,
        signal_assessment=state.signal_assessment,
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=swing_analysis_dto.SignalAssessmentAvailability(
            status=swing_analysis_dto.SignalAssessmentStatus.AVAILABLE
        ),
    )
    return state


def test_canonical_evidence_includes_both_groups_when_both_built():
    engine = _RecordingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_source_availability_use_case(),
    )

    result = composer.recompose_after_evidence(_request(), state)

    assert len(engine.calls) == 1
    canonical_evidence = engine.calls[0]["canonical_evidence"]
    assert canonical_evidence is not None
    assert canonical_evidence.setup is not None
    assert canonical_evidence.flow is not None
    assert canonical_evidence.setup.availability.assessments[0].source_family == "candles"
    assert result.signal_assessment.score == 91


def test_canonical_evidence_setup_stays_none_when_setup_evidence_not_built():
    engine = _RecordingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=None,
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_source_availability_use_case(),
    )

    composer.recompose_after_evidence(_request(), state)

    canonical_evidence = engine.calls[0]["canonical_evidence"]
    assert canonical_evidence.setup is None
    assert canonical_evidence.flow is not None


def test_no_rescore_when_no_evidence_built():
    # No built evidence at all -> canonical_evidence is None -> the rescore
    # branch must not run (fast-path score stays untouched).
    engine = _RecordingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=None,
        built_flow_evidence=None,
        source_availability_use_case=_source_availability_use_case(),
    )

    result = composer.recompose_after_evidence(_request(), state)

    assert engine.calls == []
    assert result.signal_assessment.score == 50


def test_missing_source_availability_use_case_rescores_with_unknown_shadow_availability():
    engine = _RecordingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=None,
    )

    result = composer.recompose_after_evidence(_request(), state)

    # SignalEngine is called exactly once
    assert len(engine.calls) == 1

    # canonical setup/flow evidence is supplied
    canonical_evidence = engine.calls[0]["canonical_evidence"]
    assert canonical_evidence is not None
    assert canonical_evidence.setup is not None
    assert canonical_evidence.flow is not None

    # each required source assessment is UNKNOWN
    setup_assessments = canonical_evidence.setup.availability.assessments
    assert len(setup_assessments) == 1
    assert setup_assessments[0].status == SourceAvailabilityStatus.UNKNOWN

    flow_assessments = canonical_evidence.flow.availability.assessments
    assert len(flow_assessments) == 2
    assert flow_assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert flow_assessments[1].status == SourceAvailabilityStatus.UNKNOWN

    # every UNKNOWN assessment has is_authoritative is False
    assert setup_assessments[0].is_authoritative is False
    assert flow_assessments[0].is_authoritative is False
    assert flow_assessments[1].is_authoritative is False

    # availability_enforcement == SHADOW
    from src.domain.value_objects.evidence_source_availability import AvailabilityEnforcementMode
    assert result.signal_assessment.availability_enforcement == AvailabilityEnforcementMode.SHADOW

    # built evidence is not removed
    assert result.built_setup_evidence is not None
    assert result.built_flow_evidence is not None


def test_bandar_contributor_flows_into_flow_group_availability():
    engine = _RecordingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=None,
        built_flow_evidence=_built_flow_evidence(has_bandar_contributor=True),
        source_availability_use_case=_source_availability_use_case(),
    )

    composer.recompose_after_evidence(_request(), state)

    flow_group = engine.calls[0]["canonical_evidence"].flow
    assert flow_group.availability.unassessed_contributors == ("bandar_detector",)
    assert flow_group.availability.all_authoritative is False


def test_trade_setup_recomposition_runs_alongside_canonical_evidence():
    engine = _RecordingSignalEngine(response_score=91)
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_source_availability_use_case(),
    )

    result = composer.recompose_after_evidence(_request(), state)

    assert result.verdict.trade_setup == "SENTINEL_TRADE_SETUP"
    assert result.signal_assessment.score == 91


# --- Swing composer fallback/error tests (Step 4 tests) ---------------------------

def test_rescores_when_availability_use_case_is_none():
    # 9. Built setup and flow evidence are rescored when the availability use case is None.
    from src.application.services.signal_engine import SignalEngine
    engine = SignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )
    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=None,
    )
    assert state.signal_assessment.score == 50

    result = composer.recompose_after_evidence(_request(), state)
    assert result.signal_assessment.score != 50


def test_operational_availability_failure_still_rescored():
    # 10. Operational availability failure still rescored with canonical evidence.
    from src.application.services.signal_engine import SignalEngine
    engine = SignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )

    class _FailingUseCase:
        def execute(self, **kwargs):
            raise RuntimeError("Database timeout")

    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_FailingUseCase(),
    )

    result = composer.recompose_after_evidence(_request(), state)
    assert result.signal_assessment.score != 50
    assert result.signal_assessment.setup_source_availability.assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert result.signal_assessment.flow_source_availability.assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert result.signal_assessment.flow_source_availability.assessments[1].status == SourceAvailabilityStatus.UNKNOWN


def test_contract_value_error_escapes_in_swing():
    # 11. Contract ValueError still escapes.
    import pytest
    from src.application.services.signal_engine import SignalEngine
    engine = SignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )

    class _ContractErrorUseCase:
        def execute(self, **kwargs):
            raise ValueError("Invalid format")

    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_ContractErrorUseCase(),
    )

    with pytest.raises(ValueError, match="Invalid format"):
        composer.recompose_after_evidence(_request(), state)


def test_current_and_unknown_availability_produce_identical_directional_score_in_swing():
    # 12. CURRENT and UNKNOWN availability produce identical directional
    #     score. HIGH-2 explicitly supersedes the coverage/entry-quality-
    #     identical guarantee this test previously enforced:
    #     signal_authority_coverage is now availability-gated by design.
    from src.application.services.signal_engine import SignalEngine
    engine = SignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(), signal_engine=engine
    )

    state_current = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_source_availability_use_case(),
    )
    result_current = composer.recompose_after_evidence(_request(), state_current)

    state_unknown = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=None,
    )
    result_unknown = composer.recompose_after_evidence(_request(), state_unknown)

    a1 = result_current.signal_assessment
    a2 = result_unknown.signal_assessment
    assert a1.score == a2.score


def test_recompose_after_evidence_forwards_market_context_to_signal_engine():
    from src.domain.value_objects.market_context import MarketContext, MarketRegime

    _RISK_OFF_CONTEXT = MarketContext(
        regime=MarketRegime.RISK_OFF,
        conviction=0.9,
        factors=(),
        signal_multiplier=0.4,
        gate_tightening=True,
        as_of_date=SNAP,
        staleness_warning=None,
        coverage_warning=None,
    )

    engine = _RecordingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(),
        signal_engine=engine,
    )

    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_source_availability_use_case(),
    )
    state.market_regime = _RISK_OFF_CONTEXT

    composer.recompose_after_evidence(_request(), state)

    assert len(engine.calls) == 1
    assert engine.calls[0].get("market_context") is _RISK_OFF_CONTEXT


def test_recompose_after_evidence_failure_clears_pre_existing_trade_setup():
    class FailingSignalEngine:
        def foreign_flow_quality_from_accum_score(self, score):
            return None
        def bandar_max_range(self, n):
            return 0
        def evaluate_with_context(self, ticker, signal_context, market_context=None, **kwargs):
            raise RuntimeError("rescore boom")

    engine = FailingSignalEngine()
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_RecordingRiskTradeSetupComposer(),
        signal_engine=engine,
    )

    # Pre-existing verdict and trade setup
    from src.domain.value_objects.trade_setup import TradeSetup, SetupAction
    from src.domain.value_objects.signal_assessment import SignalStrength
    pre_existing_setup = TradeSetup(
        ticker=TICKER,
        snapshot_date=SNAP,
        action=SetupAction.ENTER,
        signal_score=75,
        signal_score_raw=75,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="test",
    )

    state = _state(
        built_setup_evidence=_built_setup_evidence(),
        built_flow_evidence=_built_flow_evidence(),
        source_availability_use_case=_source_availability_use_case(),
    )
    state.trade_setup = pre_existing_setup

    composer.recompose_after_evidence(_request(), state)

    assert state.trade_setup is None
    assert state.signal_assessment is None
    assert state.market_context_signal_preview is None
    assert state.market_context_trade_setup_preview is None
    assert state.verdict.trade_setup is None
    assert state.verdict.signal_assessment is None
    assert state.verdict.market_context_signal_preview is None
    assert state.verdict.market_context_trade_setup_preview is None
    assert state.signal_assessment_availability.status == swing_analysis_dto.SignalAssessmentStatus.UNAVAILABLE
    assert state.signal_assessment_availability.unavailable_reason == swing_analysis_dto.SignalAssessmentUnavailableReason.ASSESSMENT_FAILED
