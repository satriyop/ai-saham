"""Builds typed SetupPhaseReadiness from the setup family and phase snapshot.

Layer: Application
Depends on: domain value objects only. No IO, repositories, or reason-string
parsing — readiness is derived from typed fields only.

ADR-067 §4 (Amendment 2026-08-04) — readiness resolution
--------------------------------------------------------
This evaluator no longer receives ``SetupEvidence``, and the parameter is
deleted rather than defaulted to ``None``. Keeping it would leave setup evidence
a live route to Action: readiness feeds ``DecisionPolicyService`` phase caps, so
an attached ``SetupEvidence`` could veto or downgrade an action even after
ADR-067 §1 retired ``setup_quality`` from scoring. That is production authority
through a side door, and ADR-067 §1 forbids it outside the ADR-057 promotion
lifecycle. A defaulted-``None`` parameter would close the door by convention;
deleting it closes it structurally.

Nothing observable changed when the parameter went away. The screen path already
hardcodes ``setup=None`` in its canonical evidence
(``accumulation_candidate_signal_assessor.py``), and ``plan swing`` stopped
building a ``CanonicalSignalEvidenceInput`` in ADR-067 §3, so no production
caller ever supplied setup evidence here. Measured over the 7,764 accum
window-observations captured to 2026-08-04: 7,379 ``None``, 201 INELIGIBLE,
184 UNAVAILABLE, 0 INCOMPLETE, 0 READY.

``SetupEvidence`` itself survives untouched for the ``--setup`` diagnostic lens
(ADR-067 §4); this module simply stops being one of its consumers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.value_objects.setup_phase import SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import (
    SetupPhaseReadiness,
    SetupReadinessStatus,
)

if TYPE_CHECKING:
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot

_ADVERSE_TERMINAL_PHASES = {
    SetupPhaseState.DISTRIBUTION,
    SetupPhaseState.FAILED,
}

# Why UNAVAILABLE carries a prose clause rather than an input name: this string
# reaches operators verbatim (decision_display, the TUI judge/inspect desks) and
# agents (agent_accumulation_context warnings), and it is persisted into the
# observation fingerprint. The retired value, ``"setup_evidence"``, named a
# parameter this module no longer has — a code identifier in operator copy, and
# a tombstone in the corpus. ADR-067 §4 requires both to go.
_SETUP_MATCH_NOT_EVALUATED = "setup match not evaluated"


class SetupPhaseReadinessEvaluator:
    """Evaluate one typed setup-family readiness result.

    Precedence (exact order, do not reorder):

    1. Missing/blank setup_family -> None (preserves flow-only assessment).
    2. Phase DISTRIBUTION or FAILED -> INELIGIBLE immediately. This must
       dominate every other condition below — a known adverse phase cannot be
       masked by absent evidence.
    3. Phase EXHAUSTION -> INELIGIBLE immediately. Same masking guarantee.
    4. Otherwise -> UNAVAILABLE. The setup match is not evaluated on this path
       (ADR-067 §4), so no phase/family fact can raise readiness above it.

    Rules 1-3 are unchanged from the pre-ADR-067 evaluator, bit for bit: same
    predicates, same order, same ``failed_requirements`` payloads. They are the
    branches that feed the DecisionPolicy phase caps (DISTRIBUTION/FAILED ->
    AVOID, EXHAUSTION -> WATCH) and they never read setup evidence.

    Rule 4 was previously ``setup_evidence is None -> UNAVAILABLE``, the gate in
    front of nine further rules. Those nine — required-phase-snapshot-absent,
    unavailable phase-evidence reasons, setup_match PARTIAL/NO_MATCH,
    entry_authority, phase NONE, phase membership, sequence validity, and READY
    — were only reachable once evidence was present, so with the parameter gone
    they are unreachable by construction and are deleted rather than left as
    dead branches. READY and INCOMPLETE therefore have no producer; that matches
    the measurement (0 of 7,764) rather than changing it.
    """

    def evaluate(
        self,
        *,
        setup_family: str | None,
        setup_phase: "SetupPhaseSnapshot | None",
    ) -> SetupPhaseReadiness | None:
        family = _normalize_setup_family(setup_family)
        if family is None:
            return None

        phase = setup_phase.current_phase if setup_phase is not None else None

        # 2-3: known adverse/exhausted phases dominate every other condition.
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

        # 4: the setup match is not production evidence on this path.
        return SetupPhaseReadiness(
            setup_family=family,
            status=SetupReadinessStatus.UNAVAILABLE,
            current_phase=phase,
            missing_required_inputs=(_SETUP_MATCH_NOT_EVALUATED,),
        )


def _normalize_setup_family(setup_family: str | None) -> str | None:
    if not setup_family:
        return None
    normalized = setup_family.strip().lower().replace("-", "_")
    return normalized or None
