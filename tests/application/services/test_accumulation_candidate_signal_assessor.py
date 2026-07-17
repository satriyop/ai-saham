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
        broker_daily_flow_rows=(),
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
