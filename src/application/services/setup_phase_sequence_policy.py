"""Setup phase sequence validation policy.

Layer: Application
Depends on: setup_phase_config DTOs + domain SetupPhaseState.
"""

from __future__ import annotations

from src.application.services.setup_phase_config import SetupPhaseConfig
from src.domain.value_objects.setup_phase import SetupPhaseState


def validate_setup_phase_sequence(
    setup_family: str | None,
    phase: SetupPhaseState,
    reasons: tuple[str, ...],
    previous_phases: tuple[SetupPhaseState, ...],
    config: SetupPhaseConfig,
) -> tuple[bool | None, str | None]:
    if phase in {
        SetupPhaseState.NONE,
        SetupPhaseState.FAILED,
        SetupPhaseState.DISTRIBUTION,
        SetupPhaseState.EXHAUSTION,
    }:
        return None, None
    requirement = config.requirement_for(setup_family)
    if requirement is None:
        return None, None
    if requirement.requires_reclaim_or_pivot:
        has_reclaim = any(
            "VWAP reclaim" in r or "support reclaim" in r for r in reasons
        )
        valid = phase == SetupPhaseState.BREAKOUT_CONFIRMATION and has_reclaim
        return valid, "sequence policy: trend support plus reclaim/pivot confirmation"
    if not requirement.required_sequence:
        return None, None
    seq = requirement.required_sequence
    if phase not in seq:
        valid = False
    else:
        idx = seq.index(phase)
        valid = True if idx == 0 else _contains_ordered(previous_phases, seq[:idx])
    return valid, _sequence_reason_text(seq)


def _sequence_reason_text(seq: tuple[SetupPhaseState, ...]) -> str:
    if seq == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ):
        return "sequence policy: accumulation -> compression -> breakout"
    if seq == (SetupPhaseState.COMPRESSION, SetupPhaseState.BREAKOUT_CONFIRMATION):
        return "sequence policy: compression -> breakout"
    return "sequence policy: " + " -> ".join(p.value.lower() for p in seq)


def _contains_ordered(
    values: tuple[SetupPhaseState, ...],
    required: tuple[SetupPhaseState, ...],
) -> bool:
    index = 0
    for value in values:
        if value == required[index]:
            index += 1
            if index == len(required):
                return True
    return False
