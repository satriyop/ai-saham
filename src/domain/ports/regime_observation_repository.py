"""
RegimeObservationRepository port.

Abstract interface for persisting and retrieving RegimeDetectionEvidence snapshots.
Forward labels are initially None and are updated retroactively when future IHSG
candles become available (only fills NULL slots — idempotent).

Layer: Domain (Port)
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.value_objects.regime_detection_evidence import RegimeDetectionEvidence


class RegimeObservationRepository(Protocol):
    """Port for persisting regime_observations (one record per observation_date)."""

    def save(self, evidence: "RegimeDetectionEvidence") -> None:
        """Upsert a RegimeDetectionEvidence snapshot keyed by observation_date.

        If a record for the same date already exists it is replaced, so callers
        always have the latest computed evidence for that date.
        """
        ...

    def get(self, observation_date: date) -> "RegimeDetectionEvidence | None":
        """Return the stored observation for a specific date, or None."""
        ...

    def get_recent(self, limit: int = 30) -> "list[RegimeDetectionEvidence]":
        """Return the most recent observations, newest first."""
        ...

    def update_forward_labels(
        self,
        observation_date: date,
        *,
        forward_ihsg_return_5d: float | None = None,
        forward_ihsg_return_10d: float | None = None,
        forward_ihsg_return_20d: float | None = None,
    ) -> bool:
        """Retroactively fill forward label slots that are still NULL.

        Does NOT overwrite slots that are already set (idempotent fill).
        Returns True if the observation existed and at least one label was written.
        """
        ...
