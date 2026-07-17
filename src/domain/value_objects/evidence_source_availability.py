"""
EvidenceSourceAvailability / AvailabilityEnforcementMode — DQ-002 Blocker 2.

Groups one or more `SourceAvailabilityAssessment`s (per source family) under
one canonical evidence group ("setup" or "flow"). This does not average or
collapse the individual assessments: each source family's status stays
separately visible, and `all_authoritative` only reports True when every
listed assessment is itself authoritative AND there is no known contributor
to this evidence group that was left unassessed (`unassessed_contributors`)
— an evidence group can consume a real data source that has no settlement
rule yet (e.g. a live browser/API scrape, not a persisted SQLite source
family), and `all_authoritative=True` must never claim that unassessed
contributor is fine just because the sources this container does list are.

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
    """Per-evidence-group source availability, one assessment per source family.

    `unassessed_contributors`: names of real, currently-consumed contributors
    to this evidence group that have no `SourceAvailabilityAssessment` here —
    typically because they have no settlement rule (e.g. a live scrape, not a
    persisted SQLite source family). Populated only when that contributor is
    actually present/consumed for this decision, never speculatively.
    """

    evidence_group: str
    assessments: tuple[SourceAvailabilityAssessment, ...]
    unassessed_contributors: tuple[str, ...] = ()

    @property
    def all_authoritative(self) -> bool:
        return (
            bool(self.assessments)
            and not self.unassessed_contributors
            and all(assessment.is_authoritative for assessment in self.assessments)
        )

    def to_dict(self) -> dict:
        return {
            "evidence_group": self.evidence_group,
            "all_authoritative": self.all_authoritative,
            "assessments": [assessment.to_dict() for assessment in self.assessments],
            "unassessed_contributors": list(self.unassessed_contributors),
        }
