"""
Port: MacroCalendarRepository

Persistence for market-wide macroeconomic calendar events and sync markers.

Layer: Application (port definition)
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date

from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)


class MacroCalendarRepository(ABC):
    """Abstract persistence for macroeconomic calendar events."""

    @abstractmethod
    def save_events(self, events: list[MacroCalendarEvent]) -> None:
        """Upsert events by (source, source_event_id) idempotently."""
        ...

    @abstractmethod
    def has_synced_for_date(self, sync_date: date, source: str = "stockbit") -> bool:
        """Return True only when a success marker exists for sync_date.

        A partial marker does not count as synced so the next non-forced run
        retries automatically.
        """
        ...

    @abstractmethod
    def mark_synced(
        self,
        sync_date: date,
        status: str,
        source: str = "stockbit",
    ) -> None:
        """Record a sync marker (status = \"success\" | \"partial\") for the day."""
        ...

    @abstractmethod
    def get_events_in_window(
        self,
        from_date: date,
        to_date: date,
        categories: tuple[MacroEventCategory, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[MacroCalendarEvent]:
        """Return events with event_date in [from_date, to_date].

        When ``as_of_fetched_at`` is set, exclude events whose ``fetched_at``
        is after that ISO timestamp (point-in-time guard).
        """
        ...

    @abstractmethod
    def reclassify_event_categories(
        self,
        category_for_title: Callable[[str], MacroEventCategory],
    ) -> int:
        """Recompute ``category`` from each stored title via ``category_for_title``.

        Offline-safe: no network. Returns the number of rows whose category changed.
        Used when category rules update (e.g. Stockbit title → bi_rate) without a
        full remote re-fetch.
        """
        ...
