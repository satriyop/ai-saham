"""SetupPhaseReadinessEvaluator precedence tests (HIGH-2, ADR-067 §4).

Precedence after ADR-067 §4's Amendment 2026-08-04:
family -> adverse/exhausted phase (dominates everything) -> UNAVAILABLE.

Rules 1-3 (family, DISTRIBUTION/FAILED, EXHAUSTION) are preserved bit-for-bit
from the pre-ADR-067 evaluator and are what feeds the DecisionPolicy phase caps.
The evidence-gated rules that used to sit behind them (setup_match,
entry_authority, can_enter_from_phases membership, phase NONE, sequence
validity, READY) were only reachable when a ``SetupEvidence`` was supplied, and
the evaluator no longer accepts one — so they are gone, not merely unreachable.
Their retirement is asserted structurally in
``test_adr067_setup_readiness_inputs.py``.
"""

from __future__ import annotations

import pytest

from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import SetupReadinessStatus


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
def test_adverse_phase_is_ineligible(phase_state):
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=_phase(phase_state),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == phase_state


@pytest.mark.parametrize("phase_state", _ADVERSE_PHASES)
def test_adverse_phase_failed_requirement_names_the_phase(phase_state):
    """The exact payload DecisionPolicy and operator copy have always seen."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=_phase(phase_state),
    )
    assert readiness.failed_requirements == (f"phase:{phase_state.value}",)


@pytest.mark.parametrize("phase_state", _ADVERSE_PHASES)
def test_adverse_phase_dominates_regardless_of_phase_detail(phase_state):
    """Rules 2-3 must not be maskable by anything the snapshot carries."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=_phase(
            phase_state,
            sequence_valid=False,
            unavailable_evidence_reasons=("volume unavailable",),
        ),
    )
    assert readiness.status == SetupReadinessStatus.INELIGIBLE
    assert readiness.current_phase == phase_state


def test_no_family_returns_none():
    assert (
        SetupPhaseReadinessEvaluator().evaluate(
            setup_family=None,
            setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
        is None
    )
    assert SetupPhaseReadinessEvaluator().evaluate(setup_family="  ", setup_phase=None) is None


def test_family_is_normalized():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="  Foreign-Bounce ",
        setup_phase=_phase(SetupPhaseState.FAILED),
    )
    assert readiness.setup_family == "foreign_bounce"


@pytest.mark.parametrize(
    "phase_state",
    [
        SetupPhaseState.NONE,
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ],
)
def test_non_adverse_phase_is_unavailable(phase_state):
    """ADR-067 §4: the setup match is not evaluated on this path, so no
    phase/family fact can raise readiness above UNAVAILABLE. READY and
    INCOMPLETE have no producer — matching the measured 0 of 7,764."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=_phase(phase_state),
    )
    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    assert readiness.current_phase == phase_state


def test_absent_phase_snapshot_is_unavailable():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=None,
    )
    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    assert readiness.current_phase is None


def test_unavailable_reason_is_prose_not_a_code_identifier():
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.missing_required_inputs == ("setup match not evaluated",)


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
    r_low = SetupPhaseReadinessEvaluator().evaluate(setup_family="foreign-bounce", setup_phase=low)
    r_high = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce", setup_phase=high
    )
    assert r_low.status == r_high.status == SetupReadinessStatus.UNAVAILABLE
