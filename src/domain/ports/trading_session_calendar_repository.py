"""Ports for immutable trading-session calendar snapshots.

Layer: Domain ports
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence

from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)


class TradingSessionCalendarSnapshotReadError(RuntimeError):
    """Raised when a stored snapshot cannot be loaded or fails reconciliation."""


class TradingSessionCalendarSource(Protocol):
    """Strict external source that attests a complete session set for a range."""

    def fetch_snapshot(
        self,
        coverage_start: date,
        coverage_end: date,
    ) -> TradingSessionCalendarSnapshot:
        """Fetch and validate a complete snapshot. Never returns partial data.

        Raises on network failure, incomplete pagination, or malformed payload.
        """
        ...


class TradingSessionCalendarSnapshotWriteRepository(Protocol):
    def add_snapshot(self, snapshot: TradingSessionCalendarSnapshot) -> bool:
        """Persist snapshot. Returns True if inserted, False if exact idempotent hit.

        Raises on conflict with an incompatible existing row.
        """
        ...


class TradingSessionCalendarSnapshotReadRepository(Protocol):
    def get_snapshot(self, snapshot_id: str) -> TradingSessionCalendarSnapshot | None:
        """Load by ID. Raises TradingSessionCalendarSnapshotReadError on corruption."""
        ...

    def list_snapshots(self) -> Sequence[TradingSessionCalendarSnapshot]:
        """List all snapshots. Raises TradingSessionCalendarSnapshotReadError on corruption."""
        ...
