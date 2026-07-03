"""
Signal evidence value object.

Aggregate evidence contract for a ticker snapshot. Introduced in Phase 1 of the
SignalEngine refactor. Bundles per-factor FactorEvidence records with coverage
and confidence roll-ups.

This object carries NO scoring logic — it is a descriptive record produced by
SignalEvidenceBuilder (application layer).

Layer: Domain
Depends on: stdlib + FactorEvidence
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.value_objects.factor_evidence import FactorEvidence


@dataclass(frozen=True)
class SignalEvidence:
    """
    Immutable aggregate of factor evidence for one ticker snapshot.

    aggregate_confidence   mean confidence of present factors (0.0 if none present)
    coverage_ratio         present_factors / total_factors (0.0–1.0)
    missing_factors        names of factors with freshness == MISSING
    """

    ticker: str
    snapshot_date: date
    factors: tuple[FactorEvidence, ...]
    aggregate_confidence: float
    coverage_ratio: float
    missing_factors: tuple[str, ...]

    def __post_init__(self) -> None:
        if not (0.0 <= self.aggregate_confidence <= 1.0):
            raise ValueError(
                f"SignalEvidence aggregate_confidence must be 0.0–1.0, "
                f"got {self.aggregate_confidence}"
            )
        if not (0.0 <= self.coverage_ratio <= 1.0):
            raise ValueError(
                f"SignalEvidence coverage_ratio must be 0.0–1.0, "
                f"got {self.coverage_ratio}"
            )
