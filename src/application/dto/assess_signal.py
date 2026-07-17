"""
AssessSignal request/response DTOs.

Data transfer objects for the AssessSignalUseCase. These are pure data
containers with no business logic — they only hold input/output for the
use case boundary.

Layer: Application (DTO)
Depends on: domain value objects only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
from src.domain.value_objects.signal_assessment import SignalAssessment

if TYPE_CHECKING:
    from src.domain.value_objects.canonical_signal_evidence_input import (
        CanonicalSignalEvidenceInput,
    )
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.evidence_source_availability import (
        AvailabilityEnforcementMode,
        EvidenceSourceAvailability,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.signal_assessment import SignalContext


@dataclass
class AssessSignalEvidenceRequest:
    ticker: str
    snapshot_date: date
    # ADR-041 CANONICAL-EVIDENCE-BOUNDARY: the sole setup/flow evidence input.
    # There is deliberately no independent setup_evidence/
    # flow_confirmation_evidence field — those are read-only, derived below —
    # so evidence can never be supplied loose, disconnected from its
    # provenance/availability. Flags-only callers (no candidate-producing
    # evidence this run) pass canonical_evidence=None; do not fabricate
    # provenance to populate it.
    canonical_evidence: "CanonicalSignalEvidenceInput | None" = None
    signal_context: SignalContext | None = None  # for flag evaluation
    market_context: MarketContext | None = None  # for regime conditioning
    setup_family: str | None = None
    setup_phase: SetupPhaseSnapshot | None = None
    horizon: str | None = None
    sector_context_evidence: SectorContextEvidence | None = None
    company_quality_context_evidence: CompanyQualityContextEvidence | None = None

    @property
    def setup_evidence(self) -> "SetupEvidence | None":
        return (
            self.canonical_evidence.setup.evidence
            if self.canonical_evidence is not None and self.canonical_evidence.setup is not None
            else None
        )

    @property
    def flow_confirmation_evidence(self) -> "FlowConfirmationEvidence | None":
        return (
            self.canonical_evidence.flow.evidence
            if self.canonical_evidence is not None and self.canonical_evidence.flow is not None
            else None
        )


@dataclass
class AssessSignalRequest:
    """Input for signal assessment use case."""

    ticker: str
    signal_context: SignalContext | None = None


@dataclass
class AssessSignalResponse:
    """Output from signal assessment use case."""

    ticker: str
    assessment: SignalAssessment
    coverage_warning: str | None = None
    signal_score_raw: int | None = None
    # Phase 4 evidence fields — None/empty when produced by the old flat path
    evidence_confidence: float | None = None  # legacy alias for coverage_score
    active_flags: tuple[str, ...] = field(default_factory=tuple)
    flag_adjustment: int = 0
    raw_group_score: int | None = None
    raw_exact_score: float | None = None
    alpha_trigger_score: AlphaTriggerScore | None = None
    # DQ-002 Blocker 2 (shadow mode): observational source-availability facts
    # for the setup/flow evidence groups. Never read by scoring, coverage, or
    # classification logic — populated only for later HIGH-2 authority-
    # coverage enforcement to consume. None when not yet assessed (e.g. no
    # accumulation candidate for this ticker/decision).
    setup_source_availability: "EvidenceSourceAvailability | None" = None
    flow_source_availability: "EvidenceSourceAvailability | None" = None
    availability_enforcement: "AvailabilityEnforcementMode | None" = None

    @property
    def coverage_score(self) -> float | None:
        """Canonical name: evidence completeness (0.0–1.0). Alias for evidence_confidence."""
        return self.evidence_confidence

    @property
    def score(self) -> int:
        return self.assessment.score

    @property
    def strength(self) -> str:
        return self.assessment.strength.value

    @property
    def entry_quality(self) -> str:
        return self.assessment.entry_quality.value
