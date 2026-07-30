"""
SyncMacroCalendarUseCase — market-wide macroeconomic calendar sync.

Fetches Stockbit economic (and future sources) once, stores normalized events,
and records a day-level sync marker. Owns ALL workflow/policy: freshness,
orchestration, and failure aggregation. No I/O imports — ports injected.

Also re-applies title→category rules to stored rows (offline) so config rule
updates (e.g. Interest Rate Decision → bi_rate) take effect without a remote
re-fetch.

Layer: Application
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from src.application.ports.macro_calendar_provider import (
    MacroCalendarFetchError,
    MacroCalendarProvider,
)
from src.application.ports.macro_calendar_repository import MacroCalendarRepository
from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)


@dataclass(frozen=True)
class SyncMacroCalendarRequest:
    sync_date: date
    force_remote_fetch: bool = False
    source: str = "stockbit"


@dataclass(frozen=True)
class SyncMacroCalendarResponse:
    status: str  # "cached" | "success" | "partial" | "failed"
    fetched_count: int
    stored_count: int
    category_counts: dict[str, int]  # MacroEventCategory.value -> count
    errors: tuple[str, ...]
    from_cache: bool
    reclassified_count: int = 0  # rows whose category changed from current rules


class SyncMacroCalendarUseCase:
    """
    Cache-aware market-wide macro calendar sync.

    Flow:
      0. Reclassify stored titles with current rules (offline; always).
      1. If not force_remote_fetch and already synced for date → 'cached'.
      2. Otherwise fetch via provider.
         - Full success (including empty list) → save if any, mark 'success'.
         - Partial (events + error) → save partial, mark 'partial'.
         - Total failure → do not save, do not mark, status 'failed'.
      3. Marker is written only for success/partial, never on total failure.
    """

    def __init__(
        self,
        provider: MacroCalendarProvider,
        repository: MacroCalendarRepository,
        category_for_title: Callable[[str], MacroEventCategory] | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._category_for_title = category_for_title

    def execute(self, request: SyncMacroCalendarRequest) -> SyncMacroCalendarResponse:
        sync_date = request.sync_date
        source = request.source

        reclassified_count = 0
        if self._category_for_title is not None:
            reclassified_count = self._repository.reclassify_event_categories(
                self._category_for_title
            )

        if not request.force_remote_fetch and self._repository.has_synced_for_date(
            sync_date, source
        ):
            return SyncMacroCalendarResponse(
                status="cached",
                fetched_count=0,
                stored_count=0,
                category_counts={},
                errors=(),
                from_cache=True,
                reclassified_count=reclassified_count,
            )

        events: list[MacroCalendarEvent]
        errors: list[str] = []
        had_fetch_error = False

        try:
            events = self._provider.fetch_events()
        except MacroCalendarFetchError as e:
            events = list(e.partial_events)
            errors.append(e.reason)
            had_fetch_error = True
        except Exception as e:
            return SyncMacroCalendarResponse(
                status="failed",
                fetched_count=0,
                stored_count=0,
                category_counts={},
                errors=(str(e),),
                from_cache=False,
                reclassified_count=reclassified_count,
            )

        fetched_count = len(events)
        stored_count = 0
        category_counts: dict[str, int] = {}
        if events:
            self._repository.save_events(events)
            stored_count = len(events)
            for ev in events:
                key = ev.category.value
                category_counts[key] = category_counts.get(key, 0) + 1

        if not had_fetch_error:
            status = "success"
        elif events:
            status = "partial"
        else:
            status = "failed"

        if status in ("success", "partial"):
            self._repository.mark_synced(sync_date, status=status, source=source)

        return SyncMacroCalendarResponse(
            status=status,
            fetched_count=fetched_count,
            stored_count=stored_count,
            category_counts=category_counts,
            errors=tuple(errors),
            from_cache=False,
            reclassified_count=reclassified_count,
        )
