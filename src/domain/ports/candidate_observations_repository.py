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
