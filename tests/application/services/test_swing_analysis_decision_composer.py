"""Tests for SwingAnalysisDecisionComposer's shadow-mode availability attach —
DQ-002 Blocker 2.

Proves availability diagnostics reach the canonical signal-assessment
response without altering score/strength/entry_quality — the mandatory
"byte-for-byte unchanged" guarantee for this integration.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.swing_analysis_decision_composer import (
    SwingAnalysisDecisionComposer,
)
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.domain.value_objects.evidence_source_availability import (
    AvailabilityEnforcementMode,
    EvidenceSourceAvailability,
)
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.source_availability import (
    SourceAvailabilityAssessment,
    SourceAvailabilityStatus,
)


def _request():
    from pathlib import Path

    return swing_analysis_dto.SwingAnalysisWorkflowRequest(
        ticker="BBCA",
        today=date(2026, 7, 17),
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


def _signal_assessment(score: int = 72) -> AssessSignalResponse:
    assessment = SignalAssessment(
        ticker="BBCA",
        score=score,
        strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("setup", 60.0), ("flow", 40.0)),
        rationale=("test rationale",),
        snapshot_date=date(2026, 7, 17),
    )
    return AssessSignalResponse(ticker="BBCA", assessment=assessment)


def _availability(status: SourceAvailabilityStatus) -> EvidenceSourceAvailability:
    return EvidenceSourceAvailability(
        evidence_group="setup",
        assessments=(
            SourceAvailabilityAssessment(
                source_family="candles",
                decision_at=datetime(2026, 7, 17, 20, 0),
                observed_through=date(2026, 7, 17),
                available_at=None,
                status=status,
                is_authoritative=status == SourceAvailabilityStatus.CURRENT,
                reason="TEST",
            ),
        ),
    )


def _composer_with_no_rescore() -> SwingAnalysisDecisionComposer:
    # signal_engine=None disables the rescore branch entirely — isolates the
    # attach logic at the end of recompose_after_evidence from any scoring
    # side effect.
    return SwingAnalysisDecisionComposer(risk_trade_setup_composer=None, signal_engine=None)


def _state_with_signal(signal_assessment: AssessSignalResponse) -> SwingAnalysisWorkflowState:
    state = SwingAnalysisWorkflowState()
    state.signal_assessment = signal_assessment
    state.verdict = swing_analysis_dto.SwingVerdict(
        trade_setup=None,
        signal_assessment=signal_assessment,
        risk_response=None,
        market_regime=None,
    )
    return state


def test_availability_attached_to_canonical_response():
    original = _signal_assessment()
    state = _state_with_signal(original)
    state.setup_source_availability = _availability(SourceAvailabilityStatus.CURRENT)

    result = _composer_with_no_rescore().recompose_after_evidence(_request(), state)

    assert result.signal_assessment.setup_source_availability is not None
    assert (
        result.signal_assessment.setup_source_availability.assessments[0].status
        == SourceAvailabilityStatus.CURRENT
    )
    assert result.signal_assessment.availability_enforcement == AvailabilityEnforcementMode.SHADOW
    # And it must also reach the canonical verdict, not just loose state.
    assert result.verdict.signal_assessment.setup_source_availability is not None


def test_availability_attach_does_not_change_score_or_entry_quality():
    original = _signal_assessment(score=72)
    state = _state_with_signal(original)
    state.setup_source_availability = _availability(SourceAvailabilityStatus.STALE)

    result = _composer_with_no_rescore().recompose_after_evidence(_request(), state)

    # Byte-for-byte unchanged on every scoring-relevant field.
    assert result.signal_assessment.score == original.score == 72
    assert result.signal_assessment.strength == original.strength
    assert result.signal_assessment.entry_quality == original.entry_quality
    assert result.signal_assessment.assessment.breakdown == original.assessment.breakdown
    assert result.signal_assessment.coverage_score == original.coverage_score


def test_no_availability_leaves_response_untouched():
    original = _signal_assessment()
    state = _state_with_signal(original)
    # setup_source_availability / flow_source_availability both remain None.

    result = _composer_with_no_rescore().recompose_after_evidence(_request(), state)

    assert result.signal_assessment is original
    assert result.signal_assessment.availability_enforcement is None


def test_identical_state_produces_identical_attached_response():
    availability = _availability(SourceAvailabilityStatus.CURRENT)
    composer = _composer_with_no_rescore()

    state_a = _state_with_signal(_signal_assessment())
    state_a.setup_source_availability = availability
    result_a = composer.recompose_after_evidence(_request(), state_a)

    state_b = _state_with_signal(_signal_assessment())
    state_b.setup_source_availability = availability
    result_b = composer.recompose_after_evidence(_request(), state_b)

    assert result_a.signal_assessment.setup_source_availability == (
        result_b.signal_assessment.setup_source_availability
    )
    assert result_a.signal_assessment.score == result_b.signal_assessment.score


class _FakeSignalEngine:
    """Deterministic stand-in for the real rescore path — score depends only
    on whether evidence groups are present, mirroring the real contract that
    availability attach must never influence."""

    def foreign_flow_quality_from_foreign_flow_score(self, score):
        return None

    def bandar_max_range(self, num_optional):
        return 6

    def evaluate_with_context(self, ticker, signal_ctx, **kwargs):
        has_evidence = (
            kwargs.get("setup_evidence") is not None
            or kwargs.get("flow_confirmation_evidence") is not None
        )
        return _signal_assessment(score=91 if has_evidence else 50)


class _FakeRiskTradeSetupComposer:
    """Deterministic stand-in proving trade_setup/mce recomposition runs
    alongside availability attach without either interfering with the
    other."""

    def __init__(self):
        self.calls: list[dict] = []

    def recompose_after_signal_rescore(self, **kwargs):
        self.calls.append(kwargs)
        return ("SENTINEL_TRADE_SETUP", kwargs["signal_assessment"], None, [])


def _real_rescore_state() -> SwingAnalysisWorkflowState:
    candidate = SimpleNamespace(
        bandar_detector=None,
        seasonal_edge=None,
        analyst_consensus=None,
        forward_estimates=None,
        current_price=None,
        foreign_flow_score=0.0,
        insider_net_buy_ratio=None,
    )
    state = SwingAnalysisWorkflowState()
    state.accumulation_candidate = candidate
    state.evidence = swing_analysis_dto.SwingEvidence(
        accumulation_candidate=candidate,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        regime_label=None,
        setup_evidence="SENTINEL_SETUP_EVIDENCE",
        flow_confirmation_evidence="SENTINEL_FLOW_EVIDENCE",
    )
    state.signal_assessment = _signal_assessment(score=50)  # pre-evidence score
    state.trade_setup = None
    state.market_context_signal_preview = None
    state.market_context_trade_setup_preview = None
    state.risk_response = None
    state.verdict = swing_analysis_dto.SwingVerdict(
        trade_setup=None,
        signal_assessment=state.signal_assessment,
        risk_response=None,
        market_regime=None,
    )
    return state


def test_real_rescore_path_with_availability_matches_real_rescore_without_it():
    # The reviewer's required scenario: exercise the ACTUAL rescore branch
    # (signal_engine present, real evidence groups, real trade-setup
    # recomposition), not the isolated signal_engine=None path, and prove
    # the rescored signal assessment / trade setup / serialization are
    # identical whether availability diagnostics are present or absent —
    # differing only in the new diagnostic fields themselves.
    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_FakeRiskTradeSetupComposer(),
        signal_engine=_FakeSignalEngine(),
    )

    state_without_availability = _real_rescore_state()
    result_without = composer.recompose_after_evidence(_request(), state_without_availability)

    state_with_availability = _real_rescore_state()
    state_with_availability.setup_source_availability = _availability(
        SourceAvailabilityStatus.CURRENT
    )
    result_with = composer.recompose_after_evidence(_request(), state_with_availability)

    # Real rescore actually ran in both cases (score moved from 50 -> 91).
    assert result_without.signal_assessment.score == 91
    assert result_with.signal_assessment.score == 91

    # Signal assessment, trade setup, and verdict are identical apart from
    # the new diagnostic fields.
    assert result_with.signal_assessment.score == result_without.signal_assessment.score
    assert result_with.signal_assessment.strength == result_without.signal_assessment.strength
    assert (
        result_with.signal_assessment.entry_quality
        == result_without.signal_assessment.entry_quality
    )
    assert (
        result_with.verdict.trade_setup
        == result_without.verdict.trade_setup
        == "SENTINEL_TRADE_SETUP"
    )

    # Serialization: identical except the new diagnostic keys.
    from src.application.services.swing_analysis_serialization import (
        signal_response_to_dict,
    )

    dict_without = signal_response_to_dict(result_without.signal_assessment)
    dict_with = signal_response_to_dict(result_with.signal_assessment)
    diagnostic_keys = {
        "setup_source_availability",
        "flow_source_availability",
        "availability_enforcement",
    }
    non_diagnostic_without = {
        k: v for k, v in dict_without.items() if k not in diagnostic_keys
    }
    non_diagnostic_with = {k: v for k, v in dict_with.items() if k not in diagnostic_keys}
    assert non_diagnostic_without == non_diagnostic_with
    assert dict_without["setup_source_availability"] is None
    assert dict_with["setup_source_availability"] is not None


def _real_source_availability_use_case():
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )
    from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
    from src.domain.value_objects.idx_market import IDX_TIMEZONE

    decision_at = datetime(2026, 7, 17, 20, 0, tzinfo=IDX_TIMEZONE)
    effective_session = EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )
    calendar = KnownTradingSessionCalendar(
        sessions=(date(2026, 7, 17),),
        coverage_start=date(2026, 7, 17),
        coverage_end=date(2026, 7, 17),
    )
    return AssessSourceAvailabilityUseCase(calendar=calendar), effective_session


def test_setup_availability_stays_none_when_setup_evidence_was_not_produced():
    # P2: availability must describe evidence that was actually produced,
    # not evidence a candidate could theoretically have produced. Only
    # flow_confirmation_evidence exists here (e.g. no setup was requested) —
    # setup_source_availability must remain None even though
    # accumulation_candidate and source_availability_use_case both exist.
    use_case, effective_session = _real_source_availability_use_case()
    state = _real_rescore_state()
    state.source_availability_use_case = use_case
    state.effective_session = effective_session
    state.candles = [SimpleNamespace(date=date(2026, 7, 17))]
    state.evidence = replace(state.evidence, setup_evidence=None)

    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_FakeRiskTradeSetupComposer(),
        signal_engine=_FakeSignalEngine(),
    )
    result = composer.recompose_after_evidence(_request(), state)

    assert result.setup_source_availability is None
    assert result.flow_source_availability is not None
    assert result.signal_assessment.setup_source_availability is None
    assert result.signal_assessment.flow_source_availability is not None


def test_setup_availability_computed_when_setup_evidence_was_produced():
    use_case, effective_session = _real_source_availability_use_case()
    state = _real_rescore_state()
    state.source_availability_use_case = use_case
    state.effective_session = effective_session
    state.candles = [SimpleNamespace(date=date(2026, 7, 17))]
    # state.evidence.setup_evidence is already "SENTINEL_SETUP_EVIDENCE".

    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_FakeRiskTradeSetupComposer(),
        signal_engine=_FakeSignalEngine(),
    )
    result = composer.recompose_after_evidence(_request(), state)

    assert result.setup_source_availability is not None
    assert result.setup_source_availability.assessments[0].source_family == "candles"
    assert result.setup_source_availability.assessments[0].status == SourceAvailabilityStatus.CURRENT


def test_bandar_present_prevents_flow_all_authoritative_true_end_to_end():
    # P1: a real, currently-consumed contributor to flow evidence
    # (bandar_detector) that has no settlement rule must prevent
    # flow_source_availability.all_authoritative from ever reporting True,
    # even when broker_summaries/broker_daily_flow are both CURRENT.
    use_case, effective_session = _real_source_availability_use_case()
    state = _real_rescore_state()
    state.source_availability_use_case = use_case
    state.effective_session = effective_session
    state.candles = [SimpleNamespace(date=date(2026, 7, 17))]
    state.accumulation_candidate.latest_broker_date = date(2026, 7, 17)
    state.accumulation_candidate.latest_broker_daily_flow_date = date(2026, 7, 17)
    state.accumulation_candidate.bandar_detector = SimpleNamespace(broad_score=5)

    composer = SwingAnalysisDecisionComposer(
        risk_trade_setup_composer=_FakeRiskTradeSetupComposer(),
        signal_engine=_FakeSignalEngine(),
    )
    result = composer.recompose_after_evidence(_request(), state)

    flow_availability = result.signal_assessment.flow_source_availability
    assert flow_availability is not None
    assert all(a.is_authoritative for a in flow_availability.assessments)
    assert flow_availability.unassessed_contributors == ("bandar_detector",)
    assert flow_availability.all_authoritative is False
