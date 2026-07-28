"""
Port: MacroCalendarProvider

Fetches market-wide macroeconomic calendar events from a source (e.g. Stockbit
Exodus `/corpaction/economic`). Fetch + parse only — no caching or persistence.

Layer: Application (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.macro_calendar_event import MacroCalendarEvent


class MacroCalendarFetchError(Exception):
    """Raised when the macro calendar fetch fails (auth/network/parse).

    Carries partial_events so multi-source futures can still save what
    succeeded. For v1 (single Stockbit economic stream) partial_events is
    typically empty on total failure.
    """

    def __init__(
        self,
        reason: str,
        partial_events: list[MacroCalendarEvent] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.partial_events = list(partial_events or [])


class MacroCalendarProvider(ABC):
    """Fetches market-wide macroeconomic calendar events from a source."""

    @abstractmethod
    def fetch_events(self) -> list[MacroCalendarEvent]:
        """Fetch all available macro calendar events.

        Raises MacroCalendarFetchError on auth/network/total-parse failure.
        A successful HTTP response with an empty list is not an error.
        """
        ...
