"""Shared fixtures and helpers for signal evidence use case tests."""

from datetime import date

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceUseCase,
)
from src.application.use_case.assess_signal_use_case import SignalEngineConfig
from src.domain.value_objects.company_quality_context_evidence import (
    CompanyQualityContextEvidence,
)
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
from src.domain.value_objects.signal_assessment import SignalContext

SNAP = date(2026, 7, 3)


def _use_case(config: SignalEngineConfig | None = None) -> AssessSignalEvidenceUseCase:
    return AssessSignalEvidenceUseCase(config=config)


def _req(**kwargs) -> AssessSignalEvidenceRequest:
    defaults = {"ticker": "TEST", "snapshot_date": SNAP}
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
        rs_vs_ihsg_5d=1.05,
        rs_freshness=Freshness.FRESH,
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
        phase_strength=conviction,
        coverage_score=coverage,
        conviction_score=conviction,
        sequence_valid=True,
    )


def _phase_state(state: SetupPhaseState) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=state,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=0.8,
        coverage_score=0.8,
        conviction_score=0.8,
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
