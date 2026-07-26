"""Tests for AccumulationCandidateSignalAssessor."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.canonical_signal_evidence_input import (
    BrokerDailyFlowRowIdentity,
    BrokerSummaryRowIdentity,
    FlowProvenance,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
    AccumScoreBreakdown,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE


def _effective_session() -> EffectiveMarketSession:
    today = date.today()
    decision_at = datetime(today.year, today.month, today.day, 20, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=today,
        analysis_as_of=today,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _source_availability_use_case() -> AssessSourceAvailabilityUseCase:
    # A proven IDX trading session can never be a Saturday/Sunday — use the
    # most recent weekday so this fixture stays valid regardless of which
    # day the test suite actually runs on.
    today = _most_recent_weekday(date.today())
    calendar = KnownTradingSessionCalendar(
        sessions=(today,), coverage_start=today, coverage_end=today
    )
    return AssessSourceAvailabilityUseCase(calendar=calendar)


def _most_recent_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _built_flow_evidence():
    from src.application.dto.built_evidence import BuiltFlowEvidence

    today = date.today()
    signal = FlowSubSignal(
        key="cons", score=40.0, weight=40.0, direction=Direction.BULLISH, freshness=Freshness.FRESH
    )
    evidence = FlowConfirmationEvidence(
        ticker="BBCA",
        snapshot_date=today,
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
        ticker="BBCA",
        broker_summary_rows=(
            BrokerSummaryRowIdentity(ticker="BBCA", date=today, source="test"),
        ),
        broker_daily_flow_rows=(
            BrokerDailyFlowRowIdentity(ticker="BBCA", date=today, broker_code="AK", source="test"),
        ),
    )
    return BuiltFlowEvidence(evidence=evidence, provenance=provenance)


def _foreign_flow_breakdown(score: float) -> AccumScoreBreakdown:
    """Build a complete typed breakdown whose canonical derived score is *score*."""
    max_points = {
        "cons": 33.3,
        "streak": 25.0,
        "vwap": 16.7,
        "rsi": 8.3,
        "flow": 8.3,
        "inst": 12.5,
    }
    remaining = score
    components = []
    for key in ("cons", "streak", "vwap", "rsi", "flow", "inst"):
        points = min(max(remaining, 0.0), max_points[key])
        remaining -= points
        components.append(
            ForeignFlowComponentScore(
                key=key,
                score_points=points,
                max_points=max_points[key],
                status=ForeignFlowComponentStatus.AVAILABLE,
            )
        )
    if round(max(remaining, 0.0), 1) != 0.0:
        raise AssertionError(f"test score {score} exceeds fixture capacity")
    components.append(
        ForeignFlowComponentScore(
            key="bb",
            score_points=None,
            max_points=8.3,
            status=ForeignFlowComponentStatus.DISABLED,
        )
    )
    return AccumScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date.today(),
        max_score=100.0,
        components=tuple(components),
        net_buy_ratio=0.8,
        consecutive_streak=3,
        vwap_discount_pct=0.0,
        rsi=50.0,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.3,
        bci_label="STABLE",
        bci_tier1_count=2,
    )


def _make_assessor(
    flow_builder_raises: bool = False,
    signal_score: int = 60,
    setup_phase: object = None,
    accum_score: float = 50.0,
):
    """Build an AccumulationCandidateSignalAssessor with mocked dependencies."""
    from src.application.services.accumulation_candidate_signal_assessor import (
        AccumulationCandidateSignalAssessor,
    )
    signal_engine = MagicMock()
    signal_engine.evaluate_accumulation_discovery.return_value.assessment.score = signal_score

    flow_builder = MagicMock()
    if flow_builder_raises:
        flow_builder.build.side_effect = RuntimeError("flow builder failed")
    else:
        flow_builder.build.return_value = _built_flow_evidence()

    evidence_builder = MagicMock()
    evidence_builder.detect_candidate_setup_phase.return_value = setup_phase

    accum_score_uc = MagicMock()
    accum_score_uc.execute.return_value.evidence = _foreign_flow_breakdown(
        accum_score
    )

    return AccumulationCandidateSignalAssessor(
        signal_engine=signal_engine,
        flow_confirmation_builder=flow_builder,
        candidate_evidence_builder=evidence_builder,
        accum_score_uc=accum_score_uc,
    )


def _candidate(accum_score: float = 50.0) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker="BBCA",
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
        accum_score=accum_score,
        top_brokers=None,
        institutional_flag=False,
    )


def _request(
    min_accum_score: float = 30.0,
    min_accum_score_enabled: bool = True,
    min_signal_score: float = 40.0,
    min_signal_score_enabled: bool = True,
    market_context=None,
) -> AccumulationScreenRequest:
    return AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        min_accum_score=min_accum_score,
        min_accum_score_enabled=min_accum_score_enabled,
        min_signal_score=min_signal_score,
        min_signal_score_enabled=min_signal_score_enabled,
        market_context=market_context,
    )


def test_foreign_flow_score_fields_set_by_assessor():
    """Assessor sets accum_score_breakdown, accum_score, and
    foreign_flow_evidence on the candidate from the foreign-flow score use case."""
    assessor = _make_assessor(accum_score=42.0)

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.candidate.accum_score_breakdown is not None
    assert result.candidate.accum_score == 42.0
    assert result.candidate.foreign_flow_evidence is not None


def test_flow_evidence_builder_exception_returns_none():
    """Operational flow-builder failure: no evidence, hard-guard skips signal.

    ADR-047: absent canonical evidence must not invoke the signal engine
    (would raise NoProductionSignalEvidenceError). With min_signal_score
    enabled the candidate is rejected_signal rather than a fabricated pass.
    """
    assessor = _make_assessor(flow_builder_raises=True)

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.flow_evidence is None
    assert result.candidate.signal_assessment is None
    assert result.passes is False
    assert result.screen_result == "rejected_signal"
    assessor._signal_engine.evaluate_accumulation_discovery.assert_not_called()


def test_foreign_flow_threshold_rejected_before_signal():
    """Foreign-flow threshold rejection takes precedence over signal rejection."""
    assessor = _make_assessor(signal_score=60, accum_score=20.0)

    result = assessor.assess(
        _candidate(),
        request=_request(
            min_accum_score=30.0,
            min_signal_score=40.0,
        ),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.screen_result == "rejected_flow"
    assert result.passes is False


def test_signal_threshold_rejected_when_flow_passes():
    """Signal threshold rejection returns rejected_signal when flow passes."""
    assessor = _make_assessor(signal_score=30, accum_score=80.0)

    result = assessor.assess(
        _candidate(),
        request=_request(
            min_accum_score=30.0,
            min_signal_score=50.0,
        ),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.screen_result == "rejected_signal"
    assert result.passes is False


def test_passing_candidate_returns_pass():
    """Candidate that passes both thresholds returns pass."""
    assessor = _make_assessor(signal_score=60, accum_score=80.0)

    result = assessor.assess(
        _candidate(),
        request=_request(
            min_accum_score=30.0,
            min_signal_score=40.0,
        ),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.screen_result == "pass"
    assert result.passes is True


def test_setup_phase_assigned_once():
    """Setup phase is assigned to the candidate by the assessor."""
    phase_mock = MagicMock()
    phase_mock.value = "ACCUMULATION"
    assessor = _make_assessor(setup_phase=phase_mock, accum_score=80.0)

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.candidate.setup_phase is not None
    assert result.candidate.setup_phase.value == "ACCUMULATION"
    assert result.passes is True


# --- Screen assessor fallback/error tests (Step 5 tests) --------------------------

def _make_assessor_real_engine(
    flow_builder_raises: bool = False,
    setup_phase: object = None,
    accum_score: float = 50.0,
):
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.accumulation_candidate_signal_assessor import (
        AccumulationCandidateSignalAssessor,
    )
    signal_engine = SignalEngine()

    flow_builder = MagicMock()
    if flow_builder_raises:
        flow_builder.build.side_effect = RuntimeError("flow builder failed")
    else:
        flow_builder.build.return_value = _built_flow_evidence()

    evidence_builder = MagicMock()
    evidence_builder.detect_candidate_setup_phase.return_value = setup_phase

    accum_score_uc = MagicMock()
    accum_score_uc.execute.return_value.evidence = _foreign_flow_breakdown(
        accum_score
    )

    return AccumulationCandidateSignalAssessor(
        signal_engine=signal_engine,
        flow_confirmation_builder=flow_builder,
        candidate_evidence_builder=evidence_builder,
        accum_score_uc=accum_score_uc,
    )


def test_flow_evidence_with_missing_availability_reaches_signal_engine():
    # 13. Flow evidence plus missing availability use case still reaches SignalEngine.
    assessor = _make_assessor()

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )

    assessor._signal_engine.evaluate_accumulation_discovery.assert_called_once()
    kwargs = assessor._signal_engine.evaluate_accumulation_discovery.call_args[1]
    canonical_evidence = kwargs.get("canonical_evidence")
    assert canonical_evidence is not None
    assert canonical_evidence.flow is not None
    assert canonical_evidence.flow.availability is not None

    flow_assessments = canonical_evidence.flow.availability.assessments
    assert len(flow_assessments) == 2
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus
    assert flow_assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert flow_assessments[1].status == SourceAvailabilityStatus.UNKNOWN


def test_assess_forwards_request_market_context_to_signal_engine():
    from src.domain.value_objects.market_context import MarketContext, MarketRegime

    assessor = _make_assessor()
    as_of = date.today()
    market_context = MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=as_of,
    )

    assessor.assess(
        _candidate(),
        request=_request(market_context=market_context),
        as_of_date=as_of,
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )

    kwargs = assessor._signal_engine.evaluate_accumulation_discovery.call_args[1]
    assert kwargs.get("market_context") is market_context


def test_operational_availability_failure_still_passes_flow_evidence():
    # 14. Operational availability failure still passes flow evidence into canonical input.
    assessor = _make_assessor()

    class _FailingUseCase:
        def execute(self, **kwargs):
            raise RuntimeError("Database error")

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_FailingUseCase(),
    )

    assessor._signal_engine.evaluate_accumulation_discovery.assert_called_once()
    kwargs = assessor._signal_engine.evaluate_accumulation_discovery.call_args[1]
    canonical_evidence = kwargs.get("canonical_evidence")
    assert canonical_evidence is not None
    assert canonical_evidence.flow is not None

    flow_assessments = canonical_evidence.flow.availability.assessments
    assert len(flow_assessments) == 2
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus
    assert flow_assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert flow_assessments[1].status == SourceAvailabilityStatus.UNKNOWN


def test_current_and_unknown_availability_produce_identical_directional_score_in_screen():
    # 15. CURRENT and UNKNOWN availability produce identical directional
    #     signal score — directional score arithmetic is based on attached
    #     evidence only and is unaffected by availability. HIGH-2 explicitly
    #     supersedes the coverage-identical guarantee this test previously
    #     enforced: signal_authority_coverage is now availability-gated by
    #     design, so it legitimately differs between CURRENT and UNKNOWN.
    assessor = _make_assessor_real_engine()

    result_current = assessor.assess(
        _candidate(),
        request=_request(min_signal_score=20.0),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    result_unknown = assessor.assess(
        _candidate(),
        request=_request(min_signal_score=20.0),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )

    a1 = result_current.candidate.signal_assessment
    a2 = result_unknown.candidate.signal_assessment
    assert a1.score == a2.score


def test_flow_builder_operational_failure_results_in_missing_flow_evidence():
    # 16. Flow builder operational failure → missing evidence; pipeline hard
    # guard skips signal (ADR-047) instead of calling evaluate_accumulation_discovery
    # with canonical_evidence=None (which would raise).
    assessor = _make_assessor(flow_builder_raises=True)

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.flow_evidence is None
    assert result.candidate.signal_assessment is None
    assert result.screen_result == "rejected_signal"
    assessor._signal_engine.evaluate_accumulation_discovery.assert_not_called()


def test_flow_builder_value_error_propagates():
    # 17. Flow builder ValueError still propagates.
    import pytest
    assessor = _make_assessor()
    assessor._flow_confirmation_builder.build.side_effect = ValueError("Contract error")

    with pytest.raises(ValueError, match="Contract error"):
        assessor.assess(
            _candidate(),
            request=_request(),
            as_of_date=date.today(),
            consumed_broker_summaries=(),
            consumed_broker_daily_flows=(),
            effective_session=_effective_session(),
            source_availability_use_case=_source_availability_use_case(),
        )


# --- HIGH-2: screen evaluation ordering tests -------------------------------


def test_family_resolved_once_and_phase_detected_once_before_signal_engine():
    """HIGH-2: resolve_preliminary_setup_family_result and
    detect_candidate_setup_phase are each called exactly once, both complete
    before SignalEngine.evaluate_accumulation_discovery, and SignalEngine receives the
    exact same family and phase objects — not value-equivalent copies."""
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.application.services.accumulation_candidate_signal_assessor import (
        AccumulationCandidateSignalAssessor,
    )
    from src.domain.value_objects.accum_score_breakdown import (
        AccumScoreBreakdown,
    )

    call_order: list[str] = []
    family_result = PrimarySetupFamilyResult(
        matched_setup_families=("foreign_bounce",),
        primary_setup_family="foreign_bounce",
        setup_family_source="detected_screen_evidence",
    )
    phase_snapshot = object()  # identity sentinel — must reach SignalEngine unchanged

    evidence_builder = MagicMock()

    def _resolve_family(candidate):
        call_order.append("resolve_family")
        return family_result

    def _detect_phase(*args, **kwargs):
        call_order.append("detect_phase")
        return phase_snapshot

    evidence_builder.resolve_preliminary_setup_family_result.side_effect = _resolve_family
    evidence_builder.detect_candidate_setup_phase.side_effect = _detect_phase

    signal_engine = MagicMock()

    def _evaluate_accumulation_discovery(*args, **kwargs):
        call_order.append("signal_engine")
        assert kwargs["setup_family"] == "foreign_bounce"
        assert kwargs["setup_phase"] is phase_snapshot
        result = MagicMock()
        result.assessment.score = 60
        return result

    signal_engine.evaluate_accumulation_discovery.side_effect = _evaluate_accumulation_discovery

    flow_builder = MagicMock()
    flow_builder.build.return_value = _built_flow_evidence()

    accum_score_uc = MagicMock()
    accum_score_uc.execute.return_value.evidence = _foreign_flow_breakdown(80.0)

    assessor = AccumulationCandidateSignalAssessor(
        signal_engine=signal_engine,
        flow_confirmation_builder=flow_builder,
        candidate_evidence_builder=evidence_builder,
        accum_score_uc=accum_score_uc,
    )

    candidate = _candidate(accum_score=80.0)
    assessor.assess(
        candidate,
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )

    assert evidence_builder.resolve_preliminary_setup_family_result.call_count == 1
    assert evidence_builder.detect_candidate_setup_phase.call_count == 1
    signal_engine.evaluate_accumulation_discovery.assert_called_once()
    assert call_order == ["resolve_family", "detect_phase", "signal_engine"]
    assert candidate.setup_family_result is family_result
    assert candidate.setup_phase is phase_snapshot


def test_known_family_with_absent_setup_evidence_cannot_enter():
    """HIGH-2: the screen never fabricates SetupEvidence. A known family with
    no setup evidence must resolve typed UNAVAILABLE readiness (via the real
    SignalEngine/DecisionPolicy pipeline) and cannot produce canonical ENTER,
    even when the phase snapshot alone would otherwise look constructive."""
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState

    phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.95,
        phase_input_coverage=1.0,
        sequence_valid=True,
    )
    assessor = _make_assessor_real_engine(setup_phase=phase, accum_score=90.0)
    assessor._candidate_evidence_builder.resolve_preliminary_setup_family_result.return_value = (
        PrimarySetupFamilyResult(
            matched_setup_families=("foreign_bounce",),
            primary_setup_family="foreign_bounce",
            setup_family_source="detected_screen_evidence",
        )
    )

    result = assessor.assess(
        _candidate(accum_score=90.0),
        request=_request(min_signal_score=0.0),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )

    assessment = result.candidate.signal_assessment
    assert assessment.setup_readiness is not None
    assert assessment.setup_readiness.status.value == "UNAVAILABLE"
    assert assessment.assessment.entry_quality.value != "ENTER"


def test_unknown_family_returns_readiness_none_and_does_not_fabricate_family():
    """HIGH-2: when no setup family can be resolved (fallback UNKNOWN), the
    screen must pass setup_family=None through — readiness is None (genuine
    flow-only assessment), never a fabricated family string."""
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )

    assessor = _make_assessor_real_engine(accum_score=80.0)
    assessor._candidate_evidence_builder.resolve_preliminary_setup_family_result.return_value = (
        PrimarySetupFamilyResult(
            matched_setup_families=(),
            primary_setup_family=None,
            setup_family_source="fallback_unknown",
        )
    )

    result = assessor.assess(
        _candidate(accum_score=80.0),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )

    assert result.candidate.setup_family_result.primary_setup_family is None
    assert result.candidate.signal_assessment.setup_readiness is None
    assert result.candidate.setup_family_result.setup_family_source == "fallback_unknown"


def test_unknown_family_flow_only_attached_required_can_clear_authority_floor():
    """ADR-041 amendment: screen discovery uses ATTACHED_REQUIRED so
    intentionally unattached setup does not dilute flow-only coverage.
    With authoritative settled flow and full component coverage, coverage
    reaches 1.0 and DecisionPolicy can keep directional ENTER.
    """
    import pytest

    from src.application.dto.built_evidence import BuiltFlowEvidence
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.domain.value_objects.signal_assessment import EntryQuality
    from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

    # Use a proven weekday (never Sat/Sun) for every date in this test so the
    # availability chain resolves CURRENT/authoritative regardless of which
    # day the suite actually runs on.
    day = _most_recent_weekday(date.today())
    decision_at = datetime(day.year, day.month, day.day, 20, 0, tzinfo=IDX_TIMEZONE)
    effective_session = EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=day,
        analysis_as_of=day,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )
    calendar = KnownTradingSessionCalendar(
        sessions=(day,), coverage_start=day, coverage_end=day
    )
    source_availability_use_case = AssessSourceAvailabilityUseCase(calendar=calendar)

    strong_signal = FlowSubSignal(
        key="cons", score=90.0, weight=100.0, direction=Direction.BULLISH, freshness=Freshness.FRESH
    )
    strong_flow_evidence = FlowConfirmationEvidence(
        ticker="BBCA",
        snapshot_date=day,
        flow_signals=(strong_signal,),
        flow_score_ex_bb=90.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.90,
        capped_strength=0.90,
        group_cap=0.95,
        group_freshness=Freshness.FRESH,
    )
    provenance = FlowProvenance(
        ticker="BBCA",
        broker_summary_rows=(
            BrokerSummaryRowIdentity(ticker="BBCA", date=day, source="test"),
        ),
        broker_daily_flow_rows=(
            BrokerDailyFlowRowIdentity(ticker="BBCA", date=day, broker_code="AK", source="test"),
        ),
    )
    built_flow = BuiltFlowEvidence(evidence=strong_flow_evidence, provenance=provenance)

    assessor = _make_assessor_real_engine(accum_score=90.0)
    assessor._flow_confirmation_builder.build.return_value = built_flow
    assessor._candidate_evidence_builder.resolve_preliminary_setup_family_result.return_value = (
        PrimarySetupFamilyResult(
            matched_setup_families=(),
            primary_setup_family=None,
            setup_family_source="fallback_unknown",
        )
    )

    result = assessor.assess(
        _candidate(accum_score=90.0),
        request=_request(min_signal_score=0.0),
        as_of_date=day,
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=effective_session,
        source_availability_use_case=source_availability_use_case,
    )

    assessment = result.candidate.signal_assessment

    # Directional strength alone would classify STRONG/ENTER (score >= 70).
    assert assessment.assessment.score >= 70

    assert assessment.signal_authority_coverage == pytest.approx(1.0)
    assert assessment.setup_readiness is None
    assert assessment.assessment.entry_quality is EntryQuality.ENTER
