"""Repository port for replayable candidate evidence observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class CandidateObservation:
    ticker: str
    snapshot_date: date
    captured_at: datetime
    payload: dict


class CandidateObservationsRepository(Protocol):
    """Local repository for schema-versioned candidate observation payloads."""

    def save_many(self, observations: list[CandidateObservation]) -> None:
        """Append observations for later replay.

        Multiple rows per (ticker, snapshot_date) are allowed — each run
        captures a timestamped snapshot. get_latest() returns the most recent.
        """
        ...

    def get_latest(self, ticker: str, snapshot_date: date) -> CandidateObservation | None:
        """Return latest saved observation for ticker/date, if any."""
        ...

    def get_at(
        self,
        ticker: str,
        snapshot_date: date,
        captured_at: datetime,
    ) -> CandidateObservation | None:
        """Return the observation for ticker/date/captured_at, if any."""
        ...

    def list_recent(
        self,
        ticker: str,
        *,
        before_date: date | None = None,
        limit: int = 20,
    ) -> list[CandidateObservation]:
        """Return recent observations for ticker, newest first.

        before_date excludes same-day observations so callers can reconstruct
        prior state without reading the row currently being written.
        """
        ...

    def list_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return latest observation per ticker for the given snapshot date."""
        ...

    def list_snapshot_dates(self) -> list[date]:
        """Return snapshot dates with saved observations, oldest first."""
        ...
