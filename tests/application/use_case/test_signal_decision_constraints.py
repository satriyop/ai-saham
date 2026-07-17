from __future__ import annotations

from datetime import date

import pytest

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceUseCase,
)
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import EntryQuality

SNAP = date(2026, 7, 5)


def _excess_return(window_sessions: int, excess_return_pct: float) -> BenchmarkExcessReturn:
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


def _mctx(regime: str) -> MarketContext:
    return MarketContext(
        regime=MarketRegime(regime),
        conviction=0.70,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=SNAP,
    )


def _setup() -> SetupEvidence:
    return SetupEvidence(
        ticker="TEST",
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
        benchmark_excess_return_5_session=_excess_return(5, 1.05),
        benchmark_excess_return_20_session=_excess_return(20, 1.05),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def _flow() -> FlowConfirmationEvidence:
    sig = FlowSubSignal(
        key="cons",
        score=80.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(sig,),
        flow_score_ex_bb=80.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.80,
        capped_strength=0.80,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def test_risk_off_enter_allowed_false_caps_enter_without_mutating_score():
    response = AssessSignalEvidenceUseCase().execute(
        AssessSignalEvidenceRequest(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            flow_confirmation_evidence=_flow(),
            market_context=_mctx("RISK_OFF"),
            setup_family="foreign-bounce",
        )
    )

    assert response.assessment.score == 92
    assert response.assessment.entry_quality == EntryQuality.WATCH

    constraints = response.assessment.decision_constraints
    assert constraints is not None
    assert constraints.max_decision == "WATCH"
    assert constraints.regime == "RISK_OFF"
    assert constraints.regime_enter_allowed is False
    assert constraints.regime_size_multiplier == 0.25
    assert constraints.setup_family == "foreign_bounce"
    assert constraints.effective_size_multiplier == 0.25
    assert "RISK_OFF disables ENTER" in constraints.constraint_reasons


def test_decision_policy_receives_coverage_score_and_conviction_score_from_setup_phase():
    """DecisionPolicyService must receive explicit coverage_score and conviction_score.

    SetupPhaseSnapshot.coverage_score is passed as policy_coverage and
    SetupPhaseSnapshot.conviction_score as policy_conviction inside
    assess_signal_evidence_use_case.py. This test verifies the wiring by
    checking that a low coverage_score produces a coverage constraint reason.
    """
    from src.application.use_case.assess_signal_evidence_use_case import (
        AssessSignalEvidenceUseCase,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState

    phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.ACCUMULATION,
        previous_phase=None,
        phase_age_sessions=3,
        phase_strength=0.50,
        coverage_score=0.20,  # deliberately low — below RISK_ON min_coverage=0.70
        conviction_score=0.80,
        sequence_valid=True,
    )

    # Use RISK_OFF where code-default min_coverage=0.80 (coverage 0.20 < 0.80)
    response = AssessSignalEvidenceUseCase().execute(
        AssessSignalEvidenceRequest(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            flow_confirmation_evidence=_flow(),
            market_context=_mctx("RISK_OFF"),
            setup_family="foreign-bounce",
            setup_phase=phase,
        )
    )

    # Coverage gate should fire (0.20 < min_coverage=0.80 for RISK_OFF in code default)
    constraints = response.assessment.decision_constraints
    assert constraints is not None
    assert any("coverage" in r.lower() for r in constraints.constraint_reasons), (
        f"Expected coverage constraint reason, got: {constraints.constraint_reasons}"
    )

    # canonical property exists on SignalAssessment
    assert response.assessment.coverage_score is not None


def test_assess_signal_response_coverage_score_is_alias_for_evidence_confidence():
    """AssessSignalResponse.coverage_score must equal evidence_confidence."""
    response = AssessSignalEvidenceUseCase().execute(
        AssessSignalEvidenceRequest(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            flow_confirmation_evidence=_flow(),
        )
    )
    assert response.coverage_score == response.evidence_confidence
    assert response.coverage_score is not None


def _setup_with_excess_return(excess_return_pct: float) -> SetupEvidence:
    return SetupEvidence(
        ticker="TEST",
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
        benchmark_excess_return_5_session=_excess_return(5, excess_return_pct),
        benchmark_excess_return_20_session=_excess_return(20, excess_return_pct),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def test_poor_benchmark_excess_return_cannot_cap_enter():
    """Task HIGH-1: a deliberately poor benchmark excess return must not cap
    an otherwise identical ENTER result — the diagnostic evidence carries no
    decision authority."""
    strong_response = AssessSignalEvidenceUseCase().execute(
        AssessSignalEvidenceRequest(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup_with_excess_return(1.05),
            flow_confirmation_evidence=_flow(),
            setup_family="foreign-bounce",
        )
    )
    assert strong_response.assessment.entry_quality == EntryQuality.ENTER

    poor_response = AssessSignalEvidenceUseCase().execute(
        AssessSignalEvidenceRequest(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup_with_excess_return(-50.0),
            flow_confirmation_evidence=_flow(),
            setup_family="foreign-bounce",
        )
    )

    assert poor_response.assessment.entry_quality == EntryQuality.ENTER
    assert poor_response.assessment.score == strong_response.assessment.score
    constraints = poor_response.assessment.decision_constraints
    if constraints is not None:
        assert not any(
            "rs_policy" in r or "benchmark_excess_return" in r.lower()
            for r in constraints.constraint_reasons
        )


def test_support_reclaim_exception_no_longer_exists():
    """Task HIGH-1 removed the broken support-reclaim exception entirely —
    the config dataclass and its production authority module must be gone,
    not merely disabled."""
    import importlib

    from src.application.services import setup_phase_config

    assert not hasattr(setup_phase_config, "SetupPhaseRSPolicyConfig")
    assert not hasattr(setup_phase_config.SetupPhaseConfig(), "rs_policy_by_setup_family")
    assert not hasattr(setup_phase_config.SetupPhaseConfig(), "rs_policy_for")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.application.services.setup_phase_rs_policy")
