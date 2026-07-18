"""Builds typed SetupPhaseReadiness from setup evidence and phase snapshot.

Layer: Application
Depends on: domain value objects only. No IO, repositories, or reason-string
parsing — readiness is derived from typed fields only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.value_objects.setup_phase import SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import (
    SetupPhaseReadiness,
    SetupReadinessStatus,
)

if TYPE_CHECKING:
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot

_ADVERSE_TERMINAL_PHASES = {
    SetupPhaseState.DISTRIBUTION,
    SetupPhaseState.FAILED,
}


class SetupPhaseReadinessEvaluator:
    """Evaluate one typed setup-family readiness result per HIGH-2 contract.

    Precedence (exact order, do not reorder):

    1.  Missing/blank setup_family -> None (preserves flow-only assessment).
    2.  Phase DISTRIBUTION or FAILED -> INELIGIBLE immediately. This must
        dominate every other condition below, including missing evidence —
        a known adverse phase cannot be masked by absent/partial evidence.
    3.  Phase EXHAUSTION -> INELIGIBLE immediately. Same masking guarantee.
    4.  Missing setup_evidence -> UNAVAILABLE.
    5.  A required phase snapshot (can_enter_from_phases non-empty) that is
        absent -> UNAVAILABLE.
    6.  setup_phase.unavailable_evidence_reasons non-empty -> UNAVAILABLE.
    7.  setup_match == PARTIAL -> INCOMPLETE.
    8.  setup_match == NO_MATCH -> INELIGIBLE.
    9.  entry_authority == False -> INELIGIBLE.
    10. Phase NONE -> ordinary INELIGIBLE.
    11. Phase not in can_enter_from_phases -> INELIGIBLE.
    12. sequence_valid is False -> INELIGIBLE.
    13. Otherwise -> READY.
    """

    def evaluate(
        self,
        *,
        setup_family: str | None,
        setup_evidence: "SetupEvidence | None",
        setup_phase: "SetupPhaseSnapshot | None",
    ) -> SetupPhaseReadiness | None:
        family = _normalize_setup_family(setup_family)
        if family is None:
            return None

        phase = setup_phase.current_phase if setup_phase is not None else None

        # 2-3: known adverse/exhausted phases dominate every other condition,
        # including missing or disqualifying evidence.
        if phase in _ADVERSE_TERMINAL_PHASES:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=(f"phase:{phase.value}",),
            )
        if phase == SetupPhaseState.EXHAUSTION:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=("phase:EXHAUSTION",),
            )

        # 4: missing setup evidence.
        if setup_evidence is None:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.UNAVAILABLE,
                current_phase=phase,
                missing_required_inputs=("setup_evidence",),
            )

        can_enter_from_phases = setup_evidence.can_enter_from_phases

        # 5: a required phase snapshot that is absent.
        if can_enter_from_phases and setup_phase is None:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.UNAVAILABLE,
                current_phase=None,
                missing_required_inputs=("setup_phase",),
            )

        # 6: unavailable phase-detection evidence.
        if setup_phase is not None and setup_phase.unavailable_evidence_reasons:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.UNAVAILABLE,
                current_phase=phase,
                missing_required_inputs=setup_phase.unavailable_evidence_reasons,
            )

        # 7-8: setup match quality.
        if setup_evidence.setup_match == "PARTIAL":
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INCOMPLETE,
                current_phase=phase,
                failed_requirements=setup_evidence.failed_gates or ("setup_match:PARTIAL",),
            )
        if setup_evidence.setup_match == "NO_MATCH":
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=setup_evidence.failed_gates or ("setup_match:NO_MATCH",),
            )

        # 9: explicit entry-authority config.
        if not setup_evidence.entry_authority:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=("entry_authority:false",),
            )

        # 10: ordinary NONE phase (distinct from the adverse phases above).
        if phase == SetupPhaseState.NONE:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=("phase:NONE",),
            )

        # 11: phase outside the setup's allowed entry phases.
        if can_enter_from_phases and phase is not None and phase.value not in can_enter_from_phases:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=(
                    f"phase:{phase.value} not in {','.join(can_enter_from_phases)}",
                ),
            )

        # 12: invalid phase sequence.
        if setup_phase is not None and setup_phase.sequence_valid is False:
            return SetupPhaseReadiness(
                setup_family=family,
                status=SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=("sequence_invalid",),
            )

        # 13: everything checked out.
        return SetupPhaseReadiness(
            setup_family=family,
            status=SetupReadinessStatus.READY,
            current_phase=phase,
        )


def _normalize_setup_family(setup_family: str | None) -> str | None:
    if not setup_family:
        return None
    normalized = setup_family.strip().lower().replace("-", "_")
    return normalized or None
