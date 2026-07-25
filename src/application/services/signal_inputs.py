"""SignalInputs DTO and SignalInputsBuilder Protocol for screen adoption.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from src.domain.value_objects.evidence_source_availability import (
    AuthorityDenominatorScope,
)

if TYPE_CHECKING:
    from src.domain.value_objects.canonical_signal_evidence_input import (
        CanonicalSignalEvidenceInput,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.signal_assessment import SignalContext


@dataclass(frozen=True)
class SignalInputs:
    """Scenario-built inputs for one signal evaluation via the pipeline.

    ``canonical_evidence is None`` is first-class: no setup/flow evidence.
    The pipeline must not invoke the signal use case in that case (hard guard).
    """

    signal_context: "SignalContext"
    canonical_evidence: "CanonicalSignalEvidenceInput | None"
    setup_family: str | None = None
    setup_phase: "SetupPhaseSnapshot | None" = None
    authority_denominator_scope: AuthorityDenominatorScope = (
        AuthorityDenominatorScope.ALL_REQUIRED
    )


@runtime_checkable
class SignalInputsBuilder(Protocol):
    """Build SignalInputs for a candidate. Scenario-owned; no engine calls."""

    def build(self, candidate: object, *, as_of_date: object) -> SignalInputs:
        """Return signal inputs. May return canonical_evidence=None."""
        ...
