"""
SourceAvailabilityStatus / SourceAvailabilityAssessment — DQ-002F.

Per-source availability contract for Phase 2 authoritative inputs. Answers
one question distinct from `EffectiveMarketSession`: given a decision
timestamp and what is known about one specific source (candles, broker
summaries, enrichment caches, market context, ...), was that source actually
available, late, stale, partial, unknown, or invalid at `decision_at` — and
is it allowed to be authoritative at all (sentiment never is).

This module only defines the value object. Settlement policy (how each
source family is classified) lives in
`src/application/services/source_settlement_registry.py`; the
`AssessSourceAvailabilityUseCase` composes the two.

Layer: Domain (pure value object, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class SourceAvailabilityStatus(str, Enum):
    """Availability state of one source family at one decision timestamp."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    LATE = "LATE"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


@dataclass(frozen=True)
class SourceAvailabilityAssessment:
    """Resolved availability state for one source family at `decision_at`.

    `is_authoritative` is deliberately a separate field from `status`: a
    source can be non-authoritative for reasons that have nothing to do with
    timing (sentiment is always non-authoritative even when perfectly
    current). Callers must gate on `is_authoritative`, not on `status`
    alone.
    """

    source_family: str
    decision_at: datetime
    observed_through: date | None
    available_at: datetime | None
    status: SourceAvailabilityStatus
    is_authoritative: bool
    reason: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "source_family": self.source_family,
            "decision_at": self.decision_at.isoformat(),
            "observed_through": (
                self.observed_through.isoformat() if self.observed_through else None
            ),
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "status": self.status.value,
            "is_authoritative": self.is_authoritative,
            "reason": self.reason,
            "notes": list(self.notes),
        }
