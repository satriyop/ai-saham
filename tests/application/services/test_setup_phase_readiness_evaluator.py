"""SetupPhaseReadinessEvaluator precedence tests (HIGH-2).

The exact precedence is: family -> adverse/exhausted phase (dominates
everything) -> missing evidence -> required-phase-absent -> unavailable
phase evidence -> setup_match -> entry_authority -> phase NONE -> phase not
in can_enter_from_phases -> sequence_valid -> READY.
"""

from __future__ import annotations

from datetime import date

import pytest

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

SNAP = date(2026, 7, 17)

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
    setup_match: str = "MATCH",
    entry_authority: bool = True,
    can_enter_from_phases: tuple[str, ...] = (),
    failed_gates: tuple[str, ...] = (),
) -> SetupEvidence:
    strength = {"MATCH": 100.0, "PARTIAL": 60.0, "NO_MATCH": 20.0}[setup_match]
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match=setup_match,
        match_strength=strength,
        failed_gates=failed_gates,
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


def _phase(
    state: SetupPhaseState,
    *,
    sequence_valid: bool | None = True,
    unavailable_evidence_reasons: tuple[str, ...] = (),
) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=state,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.9,
        phase_input_coverage=1.0,
        sequence_valid=sequence_valid,
        unavailable_evidence_reasons=unavailable_evidence_reasons,
    )


_ADVERSE_PHASES = (
    SetupPhaseState.DISTRIBUTION,
    SetupPhaseState.FAILED,
    SetupPhaseState.EXHAUSTION,
)


@pytest.mark.parametrize("phase_state", _ADVERSE_PHASES)
def test_adverse_phase_dominates_missing_setup_evidence(phase_state):
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=None,
        setup_phase=_phase(phase_state),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == phase_state


@pytest.mark.parametrize("phase_state", _ADVERSE_PHASES)
def test_adverse_phase_dominates_partial_setup_match(phase_state):
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(setup_match="PARTIAL"),
        setup_phase=_phase(phase_state),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == phase_state


@pytest.mark.parametrize("phase_state", _ADVERSE_PHASES)
def test_adverse_phase_dominates_no_match_setup_match(phase_state):
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(setup_match="NO_MATCH"),
        setup_phase=_phase(phase_state),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == phase_state


@pytest.mark.parametrize("phase_state", _ADVERSE_PHASES)
def test_adverse_phase_dominates_entry_authority_false(phase_state):
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(entry_authority=False),
        setup_phase=_phase(phase_state),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == phase_state


def test_no_family_returns_none():
    assert (
        SetupPhaseReadinessEvaluator().evaluate(
            setup_family=None, setup_evidence=_evidence(), setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION)
        )
        is None
    )
    assert (
        SetupPhaseReadinessEvaluator().evaluate(
            setup_family="  ", setup_evidence=_evidence(), setup_phase=None
        )
        is None
    )


def test_missing_setup_evidence_is_unavailable_when_no_adverse_phase():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=None,
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    assert readiness.missing_required_inputs == ("setup_evidence",)


def test_required_phase_snapshot_absent_is_unavailable():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=None,
    )
    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    assert readiness.missing_required_inputs == ("setup_phase",)


def test_unavailable_phase_evidence_reasons_yield_unavailable():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(),
        setup_phase=_phase(
            SetupPhaseState.ACCUMULATION,
            unavailable_evidence_reasons=("volume unavailable",),
        ),
    )
    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    assert readiness.missing_required_inputs == ("volume unavailable",)


def test_partial_setup_match_is_incomplete():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(setup_match="PARTIAL", failed_gates=("bb_width",)),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.status == SetupReadinessStatus.INCOMPLETE
    assert readiness.failed_requirements == ("bb_width",)


def test_no_match_setup_match_is_ineligible():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(setup_match="NO_MATCH"),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE


def test_entry_authority_false_is_ineligible():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="smart-money-confirmed",
        setup_evidence=_evidence(entry_authority=False),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.failed_requirements == ("entry_authority:false",)


def test_ordinary_none_phase_is_ineligible():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(),
        setup_phase=_phase(SetupPhaseState.NONE),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == SetupPhaseState.NONE


def test_phase_not_in_can_enter_from_phases_is_ineligible():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE


def test_invalid_sequence_is_ineligible():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="pullback-continuation",
        setup_evidence=_evidence(),
        setup_phase=_phase(SetupPhaseState.ACCUMULATION, sequence_valid=False),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.failed_requirements == ("sequence_invalid",)


def test_fully_satisfied_setup_is_ready():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_evidence=_evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",)),
        setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )
    assert readiness.status == SetupReadinessStatus.READY


def test_phase_detection_strength_does_not_affect_readiness():
    # Mandatory test 7 (program-level): differing phase_detection_strength
    # with identical typed facts must not change the readiness status.
    low = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.10,
        phase_input_coverage=1.0,
        sequence_valid=True,
    )
    high = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.95,
        phase_input_coverage=1.0,
        sequence_valid=True,
    )
    ev = _evidence(can_enter_from_phases=("BREAKOUT_CONFIRMATION",))
    r_low = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce", setup_evidence=ev, setup_phase=low
    )
    r_high = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce", setup_evidence=ev, setup_phase=high
    )
    assert r_low.status == r_high.status == SetupReadinessStatus.READY
