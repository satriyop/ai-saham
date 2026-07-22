"""
AssessSignal request/response DTOs.

Data transfer objects for AssessSignalEvidenceUseCase, the canonical
staged-evidence signal assessment path. AssessSignalEvidenceRequest is the
input; AssessSignalResponse is the shared output shape. These are pure data
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
from src.domain.value_objects.evidence_source_availability import (
    AuthorityDenominatorScope,
)

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
    from src.domain.value_objects.setup_phase_readiness import SetupPhaseReadiness
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
    # ADR-041 amendment: which required PRODUCTION groups enter the authority
    # denominator. Default ALL_REQUIRED preserves swing / full-contract
    # behavior. Screen discovery passes ATTACHED_REQUIRED so intentionally
    # unattached setup does not dilute flow-only coverage.
    authority_denominator_scope: AuthorityDenominatorScope = (
        AuthorityDenominatorScope.ALL_REQUIRED
    )

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
class AssessSignalResponse:
    """Output from signal assessment use case."""

    ticker: str
    assessment: SignalAssessment
    coverage_warning: str | None = None
    signal_score_raw: int | None = None
    # HIGH-2 canonical name: production-authority coverage (0.0-1.0). None
    # when not yet supplied/evaluated for this response.
    signal_authority_coverage: float | None = None
    active_flags: tuple[str, ...] = field(default_factory=tuple)
    flag_adjustment: int = 0
    raw_group_score: int | None = None
    raw_exact_score: float | None = None
    alpha_trigger_score: AlphaTriggerScore | None = None
    # HIGH-2: typed setup-family readiness, built exactly once by
    # AssessSignalEvidenceUseCase and reused verbatim by DecisionPolicyService,
    # serialization, and persistence. None when no setup family applies (pure
    # flow-only assessment) — i.e. no resolved setup family for this ticker.
    setup_readiness: "SetupPhaseReadiness | None" = None
    # DQ-002 Blocker 2 / HIGH-2: source-availability facts for the setup/flow
    # evidence groups. Never read by directional scoring or classification —
    # HIGH-2's AssessSignalEvidenceUseCase already consumed this same
    # availability to compute signal_authority_coverage (availability_
    # enforcement=ENFORCED below); these fields are the observational record
    # of that same input, not a second independent assessment. None when not
    # yet assessed (e.g. no accumulation candidate for this ticker/decision).
    setup_source_availability: "EvidenceSourceAvailability | None" = None
    flow_source_availability: "EvidenceSourceAvailability | None" = None
    availability_enforcement: "AvailabilityEnforcementMode | None" = None

    @property
    def score(self) -> int:
        return self.assessment.score

    @property
    def strength(self) -> str:
        return self.assessment.strength.value

    @property
    def entry_quality(self) -> str:
        return self.assessment.entry_quality.value
