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

`settled_authority_fraction` is the complementary signal for authority
coverage math: it credits assessed/settled families only, so an unassessed
contributor can block a *complete* authority claim without zeroing coverage
for CURRENT broker sources that did settle.

`AvailabilityEnforcementMode` marks whether availability facts are
observational-only (`SHADOW`) or actively gate evidence (`ENFORCED`, HIGH-2).
Under `SHADOW`, availability never changes scores, coverage, or
classification — it only exposes verified facts. Under `ENFORCED` (the mode
`AssessSignalEvidenceUseCase` emits today), availability changes
`signal_authority_coverage` and downstream decision eligibility only; it
still never changes directional score, which is computed from attached
evidence exactly as before in both modes.

Layer: Domain (pure value object, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.value_objects.source_availability import SourceAvailabilityAssessment


class AvailabilityEnforcementMode(str, Enum):
    """Whether source availability facts are observational or enforced."""

    SHADOW = "SHADOW"
    ENFORCED = "ENFORCED"


class AuthorityDenominatorScope(str, Enum):
    """Which required PRODUCTION groups enter signal_authority_coverage.

    ALL_REQUIRED: every required PRODUCTION group in config stays in the
    denominator even when intentionally unattached (swing / full contract).

    ATTACHED_REQUIRED: only required PRODUCTION groups attached on this
    request enter the denominator (flow-only discovery / screen). Intentionally
    unattached groups are out of scope for this assessment — they are not
    silently treated as present, and they do not dilute coverage.
    """

    ALL_REQUIRED = "all_required"
    ATTACHED_REQUIRED = "attached_required"


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

    def __post_init__(self) -> None:
        source_families = [a.source_family for a in self.assessments]
        if len(set(source_families)) != len(source_families):
            raise ValueError(
                f"EvidenceSourceAvailability for group {self.evidence_group!r} has "
                f"duplicate source_family assessments: {source_families!r}"
            )
        decision_ats = {a.decision_at for a in self.assessments}
        if len(decision_ats) > 1:
            raise ValueError(
                f"EvidenceSourceAvailability for group {self.evidence_group!r} mixes "
                f"assessments from different decision_at values: {decision_ats!r}"
            )

    @property
    def all_authoritative(self) -> bool:
        return (
            bool(self.assessments)
            and not self.unassessed_contributors
            and all(assessment.is_authoritative for assessment in self.assessments)
        )

    @property
    def settled_authority_fraction(self) -> float:
        """Authority among assessed/settled source families only.

        Unassessed contributors (e.g. bandar_detector) do not enter this
        fraction — they only block ``all_authoritative`` (complete-authority
        claim). Empty assessments → 0.0. When every assessed family is
        authoritative → 1.0; otherwise → 0.0 (same binary rule as historical
        source-authority gating, without punishing settled sources for a
        separately named unassessed contributor).
        """
        if not self.assessments:
            return 0.0
        if all(assessment.is_authoritative for assessment in self.assessments):
            return 1.0
        return 0.0

    def to_dict(self) -> dict:
        return {
            "evidence_group": self.evidence_group,
            "all_authoritative": self.all_authoritative,
            "settled_authority_fraction": self.settled_authority_fraction,
            "assessments": [assessment.to_dict() for assessment in self.assessments],
            "unassessed_contributors": list(self.unassessed_contributors),
        }
