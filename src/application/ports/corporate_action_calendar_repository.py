"""
Port: CorporateActionCalendarRepository

Persistence for market-wide corporate action calendar events. Implementations
store events + their dated milestones in normalized tables and track sync
markers so the use case can decide whether a remote fetch is needed.

Layer: Application (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)


class CorporateActionCalendarRepository(ABC):
    """Abstract persistence for market-wide corporate action calendar events."""

    @abstractmethod
    def save_events(self, events: list[CorporateActionCalendarEvent]) -> None:
        """Upsert events and replace their date-role rows idempotently."""
        ...

    @abstractmethod
    def has_synced_for_date(
        self,
        sync_date: date,
        event_types: tuple[CorporateActionType, ...],
        source: str = "stockbit",
    ) -> bool:
        """Return True only when a sync marker exists with status == "success"
        for the canonical sync_key derived from `event_types`.

        A "partial" marker deliberately does NOT count as synced, so the next
        non-`--refresh` run automatically retries the missing types. This keeps
        the system self-healing without requiring `--refresh`.
        """
        ...

    @abstractmethod
    def has_any_sync_marker(self, source: str = "stockbit") -> bool:
        """Return True when at least one successful sync marker exists at all.

        Coarse global-sync coverage gate (DQ-004): unlike `has_synced_for_date`,
        this asks only whether the calendar has *ever* been successfully synced —
        no `sync_key`/`synced_for_date` match. It exists precisely because the
        exact event-type `sync_key` false-negatives, so it must not be replaced
        by `has_synced_for_date`. Callers use it to fail forward-label generation
        closed when nothing is known about corporate actions.
        """
        ...

    @abstractmethod
    def mark_synced(
        self,
        sync_date: date,
        event_types: tuple[CorporateActionType, ...],
        status: str,
        source: str = "stockbit",
    ) -> None:
        """Record a sync marker (status = "success" | "partial") for the
        canonical sync_key derived from `event_types` on `sync_date`."""
        ...

    @abstractmethod
    def get_events_for_ticker(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        event_types: tuple[CorporateActionType, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        """Return events for a single ticker with any date in [from_date, to_date].

        `as_of_fetched_at` (ISO timestamp), when given, excludes events whose
        `fetched_at` is after it — DQ-002G point-in-time guard so a historical
        decision cannot see a calendar event that was not yet known/synced at
        that decision time. `None` (default) preserves prior unfiltered
        behavior for existing live/diagnostic callers.
        """
        ...

    @abstractmethod
    def get_events_for_universe(
        self,
        tickers: tuple[str, ...],
        from_date: date,
        to_date: date,
        event_types: tuple[CorporateActionType, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        """Return events for a set of tickers with any date in [from_date, to_date].

        See `get_events_for_ticker` for `as_of_fetched_at` semantics.
        """
        ...

    @abstractmethod
    def get_events_by_date_role(
        self,
        from_date: date,
        to_date: date,
        date_roles: tuple[CorporateActionDateRole, ...],
        event_types: tuple[CorporateActionType, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        """Return market-wide events having a date row whose role is in
        `date_roles` and whose date is in [from_date, to_date].

        See `get_events_for_ticker` for `as_of_fetched_at` semantics.
        """
        ...
