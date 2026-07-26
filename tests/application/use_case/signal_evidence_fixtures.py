"""Shared fixtures and helpers for signal evidence use case tests."""

from datetime import date, datetime

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceUseCase,
)
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from src.domain.value_objects.canonical_signal_evidence_input import (
    BrokerDailyFlowRowIdentity,
    BrokerSummaryRowIdentity,
    CandleRowIdentity,
    CanonicalSignalEvidenceInput,
    FlowEvidenceGroupInput,
    FlowProvenance,
    SetupEvidenceGroupInput,
    SetupProvenance,
)
from src.domain.value_objects.company_quality_context_evidence import (
    CompanyQualityContextEvidence,
)
from src.domain.value_objects.evidence_source_availability import EvidenceSourceAvailability
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    SignalContext,
)
from src.domain.value_objects.source_availability import (
    SourceAvailabilityAssessment,
    SourceAvailabilityStatus,
)

SNAP = date(2026, 7, 3)
_DECISION_AT = datetime(2026, 7, 3, 20, 0)


def _current_assessment(source_family: str, observed_through: date) -> SourceAvailabilityAssessment:
    """A trivially CURRENT/authoritative assessment — these scoring-logic
    tests exercise AssessSignalEvidenceUseCase's group-scoring math, not
    availability policy, so availability just needs to be internally
    consistent with the wrapped provenance, not realistic."""
    return SourceAvailabilityAssessment(
        source_family=source_family,
        decision_at=_DECISION_AT,
        observed_through=observed_through,
        available_at=None,
        status=SourceAvailabilityStatus.CURRENT,
        is_authoritative=True,
        reason="TEST_FIXTURE",
    )


def _wrap_setup_evidence(evidence: SetupEvidence | None) -> "SetupEvidenceGroupInput | None":
    """Wrap a bare SetupEvidence into the canonical group these tests need
    (ADR-041) — trivial-but-valid provenance/availability, since these tests
    care about scoring behavior, not provenance semantics."""
    if evidence is None:
        return None
    provenance = SetupProvenance(
        ticker=evidence.ticker,
        candle_rows=(
            CandleRowIdentity(ticker=evidence.ticker, date=evidence.snapshot_date, source="test"),
        ),
        # Always populated: some fixtures set an AVAILABLE benchmark
        # excess-return by default, which BuiltSetupEvidence/
        # SetupEvidenceGroupInput require benchmark provenance for.
        benchmark_candle_rows=(
            CandleRowIdentity(
                ticker=CANONICAL_BENCHMARK_TICKER, date=evidence.snapshot_date, source="test"
            ),
        ),
    )
    availability = EvidenceSourceAvailability(
        evidence_group="setup",
        assessments=(_current_assessment("candles", evidence.snapshot_date),),
    )
    return SetupEvidenceGroupInput(evidence=evidence, provenance=provenance, availability=availability)


def _wrap_flow_evidence(
    evidence: FlowConfirmationEvidence | None,
    *,
    all_authoritative: bool = True,
    unassessed_contributors: tuple[str, ...] = (),
) -> "FlowEvidenceGroupInput | None":
    """Wrap bare FlowConfirmationEvidence into the canonical group (ADR-041).

    Defaults to a fully-authoritative availability (real broker_daily_flow row,
    both source families CURRENT) so pre-HIGH-2 scoring-logic tests keep
    exercising group-scoring math rather than incidentally exercising the
    authority-coverage gate. Pass `all_authoritative=False` for tests that
    specifically need a non-authoritative flow group. Pass
    `unassessed_contributors` (e.g. ``("bandar_detector",)``) to model a
    settled-authoritative group that still cannot claim complete authority.
    """
    if evidence is None:
        return None
    provenance = FlowProvenance(
        ticker=evidence.ticker,
        broker_summary_rows=(
            BrokerSummaryRowIdentity(
                ticker=evidence.ticker, date=evidence.snapshot_date, source="test"
            ),
        ),
        broker_daily_flow_rows=(
            ()
            if not all_authoritative
            else (
                BrokerDailyFlowRowIdentity(
                    ticker=evidence.ticker,
                    date=evidence.snapshot_date,
                    broker_code="TESTBROKER",
                    source="test",
                ),
            )
        ),
        has_bandar_contributor="bandar_detector" in unassessed_contributors,
    )
    if all_authoritative:
        daily_flow_assessment = _current_assessment("broker_daily_flow", evidence.snapshot_date)
    else:
        daily_flow_assessment = SourceAvailabilityAssessment(
            source_family="broker_daily_flow",
            decision_at=_DECISION_AT,
            observed_through=None,
            available_at=None,
            status=SourceAvailabilityStatus.UNKNOWN,
            is_authoritative=False,
            reason="TEST_FIXTURE_NO_DAILY_FLOW_ROWS",
        )
    availability = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _current_assessment("broker_summaries", evidence.snapshot_date),
            daily_flow_assessment,
        ),
        unassessed_contributors=unassessed_contributors,
    )
    return FlowEvidenceGroupInput(evidence=evidence, provenance=provenance, availability=availability)


def _available_excess_return(window_sessions: int, excess_return_pct: float) -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=window_sessions,
        ticker_return_pct=excess_return_pct,
        benchmark_return_pct=0.0,
        excess_return_pct=excess_return_pct,
        window_start=date(2026, 6, 1),
        window_end=SNAP,
        common_session_count=window_sessions + 1,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
    )


def _use_case(config: SignalEngineConfig | None = None) -> AssessSignalEvidenceUseCase:
    return AssessSignalEvidenceUseCase(config=config)


def _req(**kwargs) -> AssessSignalEvidenceRequest:
    # ADR-041: AssessSignalEvidenceRequest no longer accepts loose
    # setup_evidence/flow_confirmation_evidence — only canonical_evidence.
    # Translate the old call shape these tests use (setup_evidence=...,
    # flow_confirmation_evidence=...) into a wrapped CanonicalSignalEvidenceInput
    # so the ~90 existing scoring-logic call sites don't need individual edits.
    setup_evidence = kwargs.pop("setup_evidence", None)
    flow_confirmation_evidence = kwargs.pop("flow_confirmation_evidence", None)
    flow_all_authoritative = kwargs.pop("flow_all_authoritative", True)
    flow_unassessed_contributors = kwargs.pop("flow_unassessed_contributors", ())

    if "canonical_evidence" not in kwargs:
        if setup_evidence is not None or flow_confirmation_evidence is not None:
            kwargs["canonical_evidence"] = CanonicalSignalEvidenceInput(
                setup=_wrap_setup_evidence(setup_evidence),
                flow=_wrap_flow_evidence(
                    flow_confirmation_evidence,
                    all_authoritative=flow_all_authoritative,
                    unassessed_contributors=flow_unassessed_contributors,
                ),
            )
    else:
        if kwargs.get("canonical_evidence") is None:
            kwargs["canonical_evidence"] = None

    defaults = {
        "identity": SWING_TRADE_SETUP_IDENTITY,
        "ticker": "TEST",
        "snapshot_date": SNAP,
    }
    defaults.update(kwargs)
    return AssessSignalEvidenceRequest(**defaults)


def _setup_evidence(
    match: str = "MATCH",
    *,
    setup_name: str = "foreign-bounce",
    setup_family: str | None = None,
    entry_authority: bool = True,
    can_enter_from_phases: tuple[str, ...] = (),
) -> SetupEvidence:
    strengths = {"MATCH": 100.0, "PARTIAL": 60.0, "NO_MATCH": 20.0}
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name=setup_name,
        setup_match=match,
        match_strength=strengths[match],
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        benchmark_excess_return_5_session=_available_excess_return(5, 1.05),
        benchmark_excess_return_20_session=_available_excess_return(20, 1.05),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
        setup_family=setup_family,
        entry_authority=entry_authority,
        can_enter_from_phases=can_enter_from_phases,
    )


def _flow_evidence(
    capped_strength: float = 0.70,
    confirmation_status: str = "CONFIRMED",
) -> FlowConfirmationEvidence:
    signal = FlowSubSignal(
        key="cons",
        score=40.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(signal,),
        flow_score_ex_bb=40.0,
        confirmation_status=confirmation_status,
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=capped_strength,
        capped_strength=capped_strength,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def _ctx(**kwargs) -> SignalContext:
    return SignalContext(ticker="TEST", snapshot_date=SNAP, **kwargs)


def _setup_phase(*, coverage: float, conviction: float) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_detection_strength=conviction,
        phase_input_coverage=coverage,
        sequence_valid=True,
    )


def _phase_state(state: SetupPhaseState) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=state,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_detection_strength=0.8,
        phase_input_coverage=0.8,
        sequence_valid=True,
    )


def _sector_context(regime: str = "BULLISH") -> SectorContextEvidence:
    return SectorContextEvidence(
        sector="banking",
        peer_count=4,
        peer_tickers=("BBCA", "BBRI", "BMRI", "BBNI"),
        sector_20d_return=0.03,
        sector_vs_ihsg_20d=0.02,
        sector_breadth=0.75,
        ticker_vs_sector_rs=0.01,
        sector_regime=regime,
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=(),
    )


def _company_quality(aggregate: float = 72.0) -> CompanyQualityContextEvidence:
    return CompanyQualityContextEvidence(
        valuation_score=80.0,
        earnings_trend_score=None,
        analyst_score=70.0,
        insider_score=60.0,
        seasonality_score=55.0,
        present_axes=("valuation", "analyst", "insider", "seasonality"),
        aggregate_score=aggregate,
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=(),
    )


def _market_ctx(regime: str, gate_tightening: bool = False) -> MarketContext:
    return MarketContext(
        regime=MarketRegime(regime),
        conviction=0.6,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=gate_tightening,
        as_of_date=SNAP,
    )
