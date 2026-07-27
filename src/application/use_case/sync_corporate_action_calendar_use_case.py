"""
SyncCorporateActionCalendarUseCase — market-wide corporate action calendar sync.

Fetches the 9 market-wide Stockbit corporate action calendar endpoints once per
`saham fetch market` run (not per ticker), stores them, and records a sync
marker. Owns ALL workflow/policy: freshness/sync-marker decisions, orchestration,
and partial-failure aggregation. No I/O imports — provider and repository are
injected ports.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date

from src.application.ports.corporate_action_calendar_provider import (
    CorporateActionCalendarFetchError,
    CorporateActionCalendarProvider,
)
from src.application.ports.corporate_action_calendar_repository import (
    CorporateActionCalendarRepository,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
    CorporateActionType,
)


@dataclass(frozen=True)
class SyncCorporateActionCalendarRequest:
    event_types: tuple[CorporateActionType, ...]
    sync_date: date
    force_remote_fetch: bool = False
    source: str = "stockbit"


@dataclass(frozen=True)
class SyncCorporateActionCalendarResponse:
    status: str  # "cached" | "success" | "partial" | "failed"
    fetched_count: int
    stored_count: int
    event_type_counts: dict[str, int]  # keyed by CorporateActionType.value, only stored types
    errors: tuple[str, ...]
    from_cache: bool


class SyncCorporateActionCalendarUseCase:
    """
    Cache-aware market-wide corporate action calendar sync.

    Flow:
      1. If not force_remote_fetch and already synced for date → 'cached'.
      2. Otherwise fetch via provider.
         - Full success → save all, mark 'success'.
         - Partial failure → save the events that succeeded, mark 'partial'.
         - Total failure (no data) → do not save, do not mark, status 'failed'.
      3. Marker is written only AFTER a successful save, never on total failure.
    """

    def __init__(
        self,
        provider: CorporateActionCalendarProvider,
        repository: CorporateActionCalendarRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(
        self, request: SyncCorporateActionCalendarRequest
    ) -> SyncCorporateActionCalendarResponse:
        event_types = request.event_types
        sync_date = request.sync_date
        source = request.source

        # 1. Freshness / sync-marker decision (application-owned policy).
        if not request.force_remote_fetch and self._repository.has_synced_for_date(
            sync_date, event_types, source
        ):
            return SyncCorporateActionCalendarResponse(
                status="cached",
                fetched_count=0,
                stored_count=0,
                event_type_counts={},
                errors=(),
                from_cache=True,
            )

        # 2. Fetch — aggregate partial failures deterministically.
        events: list[CorporateActionCalendarEvent]
        failed_types: tuple[CorporateActionType, ...] = ()
        reason_by_type: dict[CorporateActionType, str] = {}

        try:
            events = self._provider.fetch_events(event_types)
        except CorporateActionCalendarFetchError as e:
            events = list(e.partial_events)
            failed_types = e.failed_event_types
            reason_by_type = dict(e.reason_by_type)
        except Exception as e:  # total failure — do not save, do not mark
            return SyncCorporateActionCalendarResponse(
                status="failed",
                fetched_count=0,
                stored_count=0,
                event_type_counts={},
                errors=(str(e),),
                from_cache=False,
            )

        fetched_count = len(events)

        # 3. Save whatever succeeded (partial results are kept, not discarded).
        stored_count = 0
        event_type_counts: dict[str, int] = {}
        if events:
            self._repository.save_events(events)
            stored_count = len(events)
            for ev in events:
                key = ev.event_type.value
                event_type_counts[key] = event_type_counts.get(key, 0) + 1

        # 4. Determine final status.
        errors = tuple(f"{et.value}:{reason}" for et, reason in reason_by_type.items())
        if not failed_types:
            status = "success"
        elif events:
            status = "partial"
        else:
            status = "failed"

        # 5. Mark synced only when something was actually attempted/saved.
        if status in ("success", "partial"):
            self._repository.mark_synced(sync_date, event_types, status=status, source=source)

        return SyncCorporateActionCalendarResponse(
            status=status,
            fetched_count=fetched_count,
            stored_count=stored_count,
            event_type_counts=event_type_counts,
            errors=errors,
            from_cache=False,
        )
