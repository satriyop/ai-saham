"""
MarketContextRepository port.

Abstract interface for persisting and retrieving MarketContext snapshots.
Infrastructure layer provides the concrete SQLite implementation.

Layer: Domain (Port)
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext


class MarketContextRepository(Protocol):
    """Port for persisting MarketContext snapshots (one canonical record per date)."""

    def save(self, context: "MarketContext") -> None:
        """Upsert a MarketContext snapshot keyed by as_of_date.

        If a record for the same date already exists it is overwritten,
        so callers always have the latest evaluation for that date.
        """
        ...

    def get(self, as_of_date: date) -> "MarketContext | None":
        """Return the stored snapshot for a specific date, or None."""
        ...

    def get_recent(self, limit: int = 30) -> "list[MarketContext]":
        """Return the most recent snapshots, newest first."""
        ...
