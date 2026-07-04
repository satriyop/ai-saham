"""
Factor evidence value object.

Canonical evidence contract for a single signal factor. Introduced in Phase 1
of the SignalEngine refactor. Annotates a component score with direction,
strength, confidence, freshness, provenance, and human-readable rationale.

This object carries NO scoring logic — it is a descriptive record produced by
SignalEvidenceBuilder (application layer) from scores already computed by
AssessSignalUseCase.

Layer: Domain
Depends on: stdlib only (dataclasses, enum)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

_E = TypeVar("_E")


def _safe_enum(enum_cls: type[_E], value: object, default: _E) -> _E:
    """Return enum member for value, falling back to default for unknown values."""
    try:
        return enum_cls(value)  # type: ignore[call-arg]
    except (ValueError, KeyError):
        return default


class Direction(str, Enum):
    """Directional lean of a factor's evidence."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Freshness(str, Enum):
    """Data freshness state for a factor."""

    FRESH = "FRESH"
    # STALE is defined for Phase 7 cache-date staleness detection.
    # Phase 1 only produces FRESH or MISSING (no cache date in SignalContext yet).
    STALE = "STALE"
    MISSING = "MISSING"


class Horizon(str, Enum):
    """Time horizon over which a factor's data is meaningful."""

    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


@dataclass(frozen=True)
class FactorEvidence:
    """
    Immutable evidence record for one signal factor.

    strength     0.0–1.0 (component_score / 100)
    confidence   0.0 when missing, 1.0 when present (Phase 1 binary)
    raw_fields   (key, value) pairs as strings for auditability
    """

    name: str
    group: str
    direction: Direction
    strength: float
    confidence: float
    freshness: Freshness
    horizon: Horizon
    source: str
    rationale: str
    raw_fields: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(
                f"FactorEvidence strength must be 0.0–1.0, got {self.strength}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"FactorEvidence confidence must be 0.0–1.0, got {self.confidence}"
            )
        for entry in self.raw_fields:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise ValueError(
                    f"FactorEvidence raw_fields entries must be 2-tuples, got {entry!r}"
                )
            key, value = entry
            if not (isinstance(key, str) and isinstance(value, str)):
                raise ValueError(
                    f"FactorEvidence raw_fields entries must be 2-tuples of strings, "
                    f"got {entry!r}"
                )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "group": self.group,
            "direction": self.direction.value,
            "strength": round(self.strength, 4),
            "confidence": round(self.confidence, 4),
            "freshness": self.freshness.value,
            "horizon": self.horizon.value,
            "source": self.source,
            "rationale": self.rationale,
            "raw_fields": list(self.raw_fields),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FactorEvidence":
        """Reconstruct from a persisted dict with schema-evolution tolerance.

        Unknown enum values fall back to safe defaults so older snapshots render
        without crashing when new enum variants are added in later phases.
        """
        return cls(
            name=data["name"],
            group=data.get("group", "unknown"),
            direction=_safe_enum(Direction, data.get("direction", "NEUTRAL"), Direction.NEUTRAL),
            strength=float(data.get("strength", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            freshness=_safe_enum(Freshness, data.get("freshness", "MISSING"), Freshness.MISSING),
            horizon=_safe_enum(Horizon, data.get("horizon", "DAILY"), Horizon.DAILY),
            source=data.get("source", ""),
            rationale=data.get("rationale", ""),
            raw_fields=tuple(tuple(pair) for pair in data.get("raw_fields", [])),
        )
