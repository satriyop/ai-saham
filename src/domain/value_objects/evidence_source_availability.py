"""
EvidenceSourceAvailability / AvailabilityEnforcementMode — DQ-002 Blocker 2.

Groups one or more `SourceAvailabilityAssessment`s (per source family) under
one canonical evidence group ("setup" or "flow"). This does not average or
collapse the individual assessments: each source family's status stays
separately visible, and `all_authoritative` only reports True when every
assessment in the group is itself authoritative.

`AvailabilityEnforcementMode` marks whether availability facts are currently
observational-only (`SHADOW`) or actively gate evidence (a later, unstarted
HIGH-2 phase). Shadow mode never changes scores, coverage, or classification;
it only exposes verified facts for later authority-coverage enforcement.

Layer: Domain (pure value object, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.value_objects.source_availability import SourceAvailabilityAssessment


class AvailabilityEnforcementMode(str, Enum):
    """Whether source availability facts are observational or enforced."""

    SHADOW = "SHADOW"


@dataclass(frozen=True)
class EvidenceSourceAvailability:
    """Per-evidence-group source availability, one assessment per source family."""

    evidence_group: str
    assessments: tuple[SourceAvailabilityAssessment, ...]

    @property
    def all_authoritative(self) -> bool:
        return bool(self.assessments) and all(
            assessment.is_authoritative for assessment in self.assessments
        )

    def to_dict(self) -> dict:
        return {
            "evidence_group": self.evidence_group,
            "all_authoritative": self.all_authoritative,
            "assessments": [assessment.to_dict() for assessment in self.assessments],
        }
