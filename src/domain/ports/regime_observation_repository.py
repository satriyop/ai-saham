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
    """Port for persisting regime_observations (one row per observation_date + cohort)."""

    def save(self, evidence: "RegimeDetectionEvidence") -> None:
        """Upsert a RegimeDetectionEvidence snapshot keyed by (observation_date, cohort).

        Evidence carries cohort identity fields (semantic_compatibility_id,
        observation_contract, universe_name, benchmark_ticker). On conflict the
        detection fields are replaced while forward labels are preserved via
        COALESCE when still NULL.
        """
        ...

    def get(
        self,
        observation_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> "RegimeDetectionEvidence | None":
        """Return the stored observation for a date, optionally scoped to a cohort.

        When semantic_compatibility_id is given, returns an exact cohort match.
        When None, returns the sole row for that date if exactly one exists;
        returns None when multiple cohort rows exist (ambiguous).
        """
        ...

    def get_recent(
        self,
        limit: int = 30,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> "list[RegimeDetectionEvidence]":
        """Return the most recent observations, newest first.

        When semantic_compatibility_id is given, results are filtered to that cohort.
        When None, all cohorts may be mixed — callers that need a single cohort must
        pass semantic_compatibility_id explicitly.
        """
        ...

    def update_forward_labels(
        self,
        observation_date: date,
        *,
        forward_ihsg_return_5d: float | None = None,
        forward_ihsg_return_10d: float | None = None,
        forward_ihsg_return_20d: float | None = None,
        semantic_compatibility_id: str = "",
    ) -> bool:
        """Retroactively fill forward label slots that are still NULL.

        Does NOT overwrite slots that are already set (idempotent fill).
        Returns True if the observation existed and at least one label was written.
        """
        ...
