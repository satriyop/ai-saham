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
    """Port for persisting MarketContext snapshots (one row per as_of_date + cohort)."""

    def save(
        self,
        context: "MarketContext",
        *,
        semantic_compatibility_id: str = "",
        observation_contract: str = "",
        universe_name: str = "",
        benchmark_ticker: str = "",
    ) -> None:
        """Upsert a MarketContext snapshot keyed by (as_of_date, cohort).

        Cohort identity kwargs are persisted alongside the snapshot without
        mutating the MarketContext value object.
        """
        ...

    def get(
        self,
        as_of_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> "MarketContext | None":
        """Return the stored snapshot for a date, optionally scoped to a cohort.

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
    ) -> "list[MarketContext]":
        """Return the most recent snapshots, newest first.

        When semantic_compatibility_id is given, results are filtered to that cohort.
        When None, all cohorts may be mixed — callers that need a single cohort must
        pass semantic_compatibility_id explicitly.
        """
        ...
