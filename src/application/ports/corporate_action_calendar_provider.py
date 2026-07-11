"""
Port: CorporateActionCalendarProvider

Fetches market-wide corporate action calendar events from a source (e.g. the
Stockbit Exodus market-wide corpaction endpoints). Fetch + parse only — the
provider owns no caching or persistence; that is the repository's job.

Lives in application/ports (matching the existing precedent
corporate_action_repository.py, which is also application-layer despite being a
"repository" for a domain concept).

Layer: Application (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
    CorporateActionType,
)


class CorporateActionCalendarFetchError(Exception):
    """Raised by providers when one or more requested event types failed to fetch.

    Carries partial results so the use case can still save what succeeded
    and report which event types failed and why (deterministic partial-failure
    contract — see docs/stockbit_api_data.md gotchas for why Stockbit endpoints
    can silently return None on auth/network failure instead of raising).
    """

    def __init__(
        self,
        partial_events: list[CorporateActionCalendarEvent],
        failed_event_types: tuple[CorporateActionType, ...],
        reason_by_type: dict[CorporateActionType, str],
    ) -> None:
        super().__init__(f"Failed to fetch: {list(failed_event_types)}")
        self.partial_events = partial_events
        self.failed_event_types = failed_event_types
        self.reason_by_type = reason_by_type


class CorporateActionCalendarProvider(ABC):
    """Fetches market-wide corporate action calendar events from a source."""

    @abstractmethod
    def fetch_events(
        self, event_types: tuple[CorporateActionType, ...]
    ) -> list[CorporateActionCalendarEvent]:
        """Fetch events for the given types. Raises CorporateActionCalendarFetchError
        (with partial_events populated) if 1+ requested types failed to fetch while
        others succeeded, or if all failed (partial_events=[] in that case)."""
        ...
