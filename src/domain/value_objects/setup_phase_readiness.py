"""Typed setup-family readiness value object.

Layer: Domain
Depends on: stdlib + SetupPhaseState only. No IO, policy orchestration, or
reason-string parsing.

Replaces generic phase coverage/conviction floors (HIGH-2). Readiness is a
typed classification, never a float, and never derived by parsing
`SetupPhaseSnapshot.reasons`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.domain.value_objects.setup_phase import SetupPhaseState


class SetupReadinessStatus(str, Enum):
    READY = "READY"
    INCOMPLETE = "INCOMPLETE"
    INELIGIBLE = "INELIGIBLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SetupPhaseReadiness:
    setup_family: str
    status: SetupReadinessStatus
    current_phase: SetupPhaseState | None
    missing_required_inputs: tuple[str, ...] = field(default_factory=tuple)
    failed_requirements: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.setup_family:
            raise ValueError("SetupPhaseReadiness.setup_family cannot be empty")
        if not isinstance(self.status, SetupReadinessStatus):
            raise ValueError("SetupPhaseReadiness.status must be a SetupReadinessStatus")
        if self.status == SetupReadinessStatus.READY and (
            self.missing_required_inputs or self.failed_requirements
        ):
            raise ValueError(
                "SetupPhaseReadiness READY must have no missing inputs or failed requirements"
            )
        if self.status == SetupReadinessStatus.UNAVAILABLE and not self.missing_required_inputs:
            raise ValueError(
                "SetupPhaseReadiness UNAVAILABLE must contain at least one missing required input"
            )
        if (
            self.status in {SetupReadinessStatus.INCOMPLETE, SetupReadinessStatus.INELIGIBLE}
            and not self.failed_requirements
        ):
            raise ValueError(
                f"SetupPhaseReadiness {self.status.value} must contain at least "
                "one failed requirement"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_family": self.setup_family,
            "status": self.status.value,
            "current_phase": self.current_phase.value if self.current_phase else None,
            "missing_required_inputs": list(self.missing_required_inputs),
            "failed_requirements": list(self.failed_requirements),
        }
