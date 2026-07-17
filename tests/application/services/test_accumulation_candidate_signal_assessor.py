"""Tests for AccumulationCandidateSignalAssessor."""

from datetime import date, datetime
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
    today = date.today()
    calendar = KnownTradingSessionCalendar(
        sessions=(today,), coverage_start=today, coverage_end=today
    )
    return AssessSourceAvailabilityUseCase(calendar=calendar)


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


def _make_assessor(
    flow_builder_raises: bool = False,
    signal_score: int = 60,
    setup_phase: object = None,
    foreign_flow_score: float = 50.0,
):
    """Build an AccumulationCandidateSignalAssessor with mocked dependencies."""
    from src.application.services.accumulation_candidate_signal_assessor import (
        AccumulationCandidateSignalAssessor,
    )
    from src.domain.value_objects.foreign_flow_score_breakdown import (
        ForeignFlowScoreBreakdown,
    )

    signal_engine = MagicMock()
    signal_engine.evaluate_with_context.return_value.assessment.score = signal_score

    flow_builder = MagicMock()
    if flow_builder_raises:
        flow_builder.build.side_effect = RuntimeError("flow builder failed")
    else:
        flow_builder.build.return_value = _built_flow_evidence()

    evidence_builder = MagicMock()
    evidence_builder.detect_candidate_setup_phase.return_value = setup_phase

    foreign_flow_score_uc = MagicMock()
    foreign_flow_score_uc.execute.return_value.evidence = ForeignFlowScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date.today(),
        foreign_flow_score=foreign_flow_score,
        max_score=100.0,
        breakdown=(),
        net_buy_ratio=0.8,
        consecutive_streak=3,
        vwap_discount_pct=0.0,
        rsi=50.0,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.3,
        bci_label="STABLE",
        bci_tier1_count=2,
    )

    return AccumulationCandidateSignalAssessor(
        signal_engine=signal_engine,
        flow_confirmation_builder=flow_builder,
        candidate_evidence_builder=evidence_builder,
        foreign_flow_score_uc=foreign_flow_score_uc,
    )


def _candidate(foreign_flow_score: float = 50.0) -> AccumulationCandidate:
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
        foreign_flow_score=foreign_flow_score,
        top_brokers=None,
        institutional_flag=False,
    )


def _request(
    min_foreign_flow_score: float = 30.0,
    min_foreign_flow_score_enabled: bool = True,
    min_signal_score: float = 40.0,
    min_signal_score_enabled: bool = True,
) -> AccumulationScreenRequest:
    return AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        min_foreign_flow_score=min_foreign_flow_score,
        min_foreign_flow_score_enabled=min_foreign_flow_score_enabled,
        min_signal_score=min_signal_score,
        min_signal_score_enabled=min_signal_score_enabled,
    )


def test_foreign_flow_score_fields_set_by_assessor():
    """Assessor sets foreign_flow_score_breakdown, foreign_flow_score, and
    foreign_flow_evidence on the candidate from the foreign-flow score use case."""
    assessor = _make_assessor(foreign_flow_score=42.0)

    result = assessor.assess(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        effective_session=_effective_session(),
        source_availability_use_case=_source_availability_use_case(),
    )

    assert result.candidate.foreign_flow_score_breakdown is not None
    assert result.candidate.foreign_flow_score == 42.0
    assert result.candidate.foreign_flow_evidence is not None


def test_flow_evidence_builder_exception_returns_none():
    """Exception in flow evidence builder does not crash; flow_evidence is None."""
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
    assert result.passes is True
    assert result.screen_result == "pass"


def test_foreign_flow_threshold_rejected_before_signal():
    """Foreign-flow threshold rejection takes precedence over signal rejection."""
    assessor = _make_assessor(signal_score=60, foreign_flow_score=20.0)

    result = assessor.assess(
        _candidate(),
        request=_request(
            min_foreign_flow_score=30.0,
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
    assessor = _make_assessor(signal_score=30, foreign_flow_score=80.0)

    result = assessor.assess(
        _candidate(),
        request=_request(
            min_foreign_flow_score=30.0,
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
    assessor = _make_assessor(signal_score=60, foreign_flow_score=80.0)

    result = assessor.assess(
        _candidate(),
        request=_request(
            min_foreign_flow_score=30.0,
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
    assessor = _make_assessor(setup_phase=phase_mock, foreign_flow_score=80.0)

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
    foreign_flow_score: float = 50.0,
):
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.accumulation_candidate_signal_assessor import (
        AccumulationCandidateSignalAssessor,
    )
    from src.domain.value_objects.foreign_flow_score_breakdown import (
        ForeignFlowScoreBreakdown,
    )

    signal_engine = SignalEngine()

    flow_builder = MagicMock()
    if flow_builder_raises:
        flow_builder.build.side_effect = RuntimeError("flow builder failed")
    else:
        flow_builder.build.return_value = _built_flow_evidence()

    evidence_builder = MagicMock()
    evidence_builder.detect_candidate_setup_phase.return_value = setup_phase

    foreign_flow_score_uc = MagicMock()
    foreign_flow_score_uc.execute.return_value.evidence = ForeignFlowScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date.today(),
        foreign_flow_score=foreign_flow_score,
        max_score=100.0,
        breakdown=(),
        net_buy_ratio=0.8,
        consecutive_streak=3,
        vwap_discount_pct=0.0,
        rsi=50.0,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.3,
        bci_label="STABLE",
        bci_tier1_count=2,
    )

    return AccumulationCandidateSignalAssessor(
        signal_engine=signal_engine,
        flow_confirmation_builder=flow_builder,
        candidate_evidence_builder=evidence_builder,
        foreign_flow_score_uc=foreign_flow_score_uc,
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

    assessor._signal_engine.evaluate_with_context.assert_called_once()
    kwargs = assessor._signal_engine.evaluate_with_context.call_args[1]
    canonical_evidence = kwargs.get("canonical_evidence")
    assert canonical_evidence is not None
    assert canonical_evidence.flow is not None
    assert canonical_evidence.flow.availability is not None

    flow_assessments = canonical_evidence.flow.availability.assessments
    assert len(flow_assessments) == 2
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus
    assert flow_assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert flow_assessments[1].status == SourceAvailabilityStatus.UNKNOWN


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

    assessor._signal_engine.evaluate_with_context.assert_called_once()
    kwargs = assessor._signal_engine.evaluate_with_context.call_args[1]
    canonical_evidence = kwargs.get("canonical_evidence")
    assert canonical_evidence is not None
    assert canonical_evidence.flow is not None

    flow_assessments = canonical_evidence.flow.availability.assessments
    assert len(flow_assessments) == 2
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus
    assert flow_assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert flow_assessments[1].status == SourceAvailabilityStatus.UNKNOWN


def test_current_and_unknown_shadow_availability_produce_identical_results_in_screen():
    # 15. CURRENT and UNKNOWN SHADOW availability produce identical:
    #     - signal score;
    #     - coverage;
    #     - entry quality;
    #     - screen result;
    #     - passes.
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
    assert a1.coverage_score == a2.coverage_score
    assert a1.assessment.entry_quality == a2.assessment.entry_quality
    assert result_current.screen_result == result_unknown.screen_result
    assert result_current.passes == result_unknown.passes


def test_flow_builder_operational_failure_results_in_missing_flow_evidence():
    # 16. Flow builder operational failure still results in missing flow evidence, preserving existing best-effort behavior.
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
    assert result.screen_result == "pass"

    assessor._signal_engine.evaluate_with_context.assert_called_once()
    kwargs = assessor._signal_engine.evaluate_with_context.call_args[1]
    assert kwargs.get("canonical_evidence") is None


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
