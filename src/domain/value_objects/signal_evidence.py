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

    SCHEMA_VERSION = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "factors": [f.to_dict() for f in self.factors],
            "aggregate_confidence": round(self.aggregate_confidence, 4),
            "coverage_ratio": round(self.coverage_ratio, 4),
            "missing_factors": list(self.missing_factors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalEvidence":
        """Reconstruct from a persisted dict with schema-evolution tolerance.

        Missing optional fields default safely; unknown enum values in nested
        FactorEvidence records fall back via _safe_enum. Raises ValueError for
        unsupported major schema versions so callers know to skip or re-fetch.
        """
        version = data.get("schema_version", 1)
        if version > cls.SCHEMA_VERSION:
            raise ValueError(
                f"SignalEvidence schema_version {version} is not supported "
                f"(max known: {cls.SCHEMA_VERSION})"
            )
        return cls(
            ticker=data["ticker"],
            snapshot_date=date.fromisoformat(data["snapshot_date"]),
            factors=tuple(FactorEvidence.from_dict(f) for f in data.get("factors", [])),
            aggregate_confidence=float(data.get("aggregate_confidence", 0.0)),
            coverage_ratio=float(data.get("coverage_ratio", 0.0)),
            missing_factors=tuple(data.get("missing_factors", [])),
        )
