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
    # Canonical identity, together with ticker/snapshot_date: two observations
    # sharing all of (ticker, snapshot_date, workflow, window_sessions,
    # data_as_of_date, config_hash) are the SAME canonical observation and a
    # second save_many() call must replace, not duplicate, the first.
    # captured_at is metadata only — never part of identity.
    workflow: str = "screen_accum"
    window_sessions: int = 0
    data_as_of_date: date | None = None
    config_hash: str = ""


class CandidateObservationsRepository(Protocol):
    """Local repository for schema-versioned candidate observation payloads."""

    def save_many(self, observations: list[CandidateObservation]) -> None:
        """Upsert observations by canonical identity for later replay.

        Identity is (ticker, snapshot_date, workflow, window_sessions,
        data_as_of_date, config_hash). Saving an observation that matches an
        existing identity replaces its payload/captured_at in place rather
        than appending a duplicate row.
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
        """Return latest observation per ticker for the given snapshot date.

        Collapses to one row per ticker — a UI/readiness display convenience.
        Do not use this for label generation: it silently drops all but the
        most-recently-captured canonical observation when a ticker has
        several (e.g. one per window_sessions). Use list_canonical_by_date()
        for anything that must cover every canonical row.
        """
        ...

    def list_all_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return all observations for the given snapshot date."""
        ...

    def list_canonical_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return every canonical observation (config_hash != '') for the date.

        Unlike list_by_date(), this does not collapse multiple canonical rows
        for the same ticker (e.g. one per window_sessions) down to the latest
        one — every canonical identity is returned. Legacy rows with no
        config_hash are excluded. This is what label generation must use so
        every recorded window gets labeled, not just the most recently
        captured one.
        """
        ...

    def list_snapshot_dates(self) -> list[date]:
        """Return snapshot dates with saved observations, oldest first."""
        ...
