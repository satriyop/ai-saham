"""Ports for immutable trading-session calendar snapshots.

Layer: Domain ports
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence

from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)


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
    def add_snapshot(self, snapshot: TradingSessionCalendarSnapshot) -> None: ...


class TradingSessionCalendarSnapshotReadRepository(Protocol):
    def get_snapshot(self, snapshot_id: str) -> TradingSessionCalendarSnapshot | None: ...

    def list_snapshots(self) -> Sequence[TradingSessionCalendarSnapshot]: ...

    def find_covering_snapshot(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> TradingSessionCalendarSnapshot | None:
        """Return a snapshot whose coverage fully spans the requested range."""
        ...
