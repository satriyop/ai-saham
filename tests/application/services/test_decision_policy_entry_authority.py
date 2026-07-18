"""
Tests for setup entry-authority enforcement (HIGH-2).

Confirmation-only setups (entry_authority=false) must not independently
produce ENTER, and phase-gated setups (can_enter_from_phases non-empty)
must only ENTER from an allowed setup_phase. This logic now lives in
SetupPhaseReadinessEvaluator (typed SetupPhaseReadiness), not
DecisionPolicyService directly — DecisionPolicyService only applies the caps
implied by the resulting typed status (covered by
test_decision_policy_setup_phase.py). Metadata is explicit SetupEvidence
input — never inferred from setup name.
"""

from __future__ import annotations

from datetime import date

from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.factor_evidence import Freshness
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import SetupReadinessStatus

SNAP = date(2026, 7, 5)

_UNAVAILABLE_EXCESS_RETURN = BenchmarkExcessReturn(
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


def _evidence(
    *,
    entry_authority: bool = True,
    can_enter_from_phases: tuple[str, ...] = (),
) -> SetupEvidence:
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
        benchmark_excess_return_5_session=_UNAVAILABLE_EXCESS_RETURN,
        benchmark_excess_return_20_session=_UNAVAILABLE_EXCESS_RETURN,
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
        setup_family="foreign_bounce",
        entry_authority=entry_authority,
        can_enter_from_phases=can_enter_from_phases,
    )


def _phase(state: SetupPhaseState) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=state,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_detection_strength=0.8,
        phase_input_coverage=1.0,
        sequence_valid=True,
    )


def test_confirmation_only_setup_is_ineligible():
    """smart-money-confirmed MATCH (entry_authority=false) must not resolve READY."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="smart-money-confirmed",
        setup_evidence=_evidence(entry_authority=False),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )

    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.failed_requirements == ("entry_authority:false",)


def test_phase_gated_setup_wrong_phase_is_ineligible():
    """foreign-bounce MATCH but setup_phase=ACCUMULATION is not READY when the
    setup requires BREAKOUT_CONFIRMATION."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )

    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == SetupPhaseState.ACCUMULATION


def test_phase_gated_setup_correct_phase_is_ready():
    """foreign-bounce MATCH with setup_phase=BREAKOUT_CONFIRMATION is READY."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )

    assert readiness.status == SetupReadinessStatus.READY


def test_missing_setup_phase_with_required_phases_is_unavailable():
    """Missing setup_phase with a non-empty can_enter_from_phases must not
    default-allow READY."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=None,
    )

    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    assert readiness.missing_required_inputs == ("setup_phase",)


def test_coiled_spring_breakout_family_still_respects_own_entry_authority():
    """coiled-spring's family YAML value changed from accumulation to breakout
    (ADR: sequence-validity policy moved to config), but readiness evaluation
    is independent of family/setup_family naming — it is sourced purely from
    the explicit SetupEvidence.entry_authority / can_enter_from_phases fields."""
    ready = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="coiled-spring",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )
    assert ready.status == SetupReadinessStatus.READY

    downgraded = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="coiled-spring",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert downgraded.status == SetupReadinessStatus.INELIGIBLE


def test_entry_authority_defaults_do_not_change_existing_behavior():
    """Backward compat: default SetupEvidence (entry_authority=True,
    can_enter_from_phases=()) with any phase resolves READY."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )

    assert readiness.status == SetupReadinessStatus.READY
