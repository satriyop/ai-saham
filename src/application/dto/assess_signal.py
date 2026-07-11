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
from typing import TYPE_CHECKING

from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
from src.domain.value_objects.signal_assessment import SignalAssessment

if TYPE_CHECKING:
    from src.domain.value_objects.signal_assessment import SignalContext


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
