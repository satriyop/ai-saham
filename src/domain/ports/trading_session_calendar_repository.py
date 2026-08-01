"""Read port for authoritative market-session calendars (path labels / readiness).

Layer: Domain port. Implementations live in infrastructure and must stay
read-only for status/readiness composition roots.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar


class TradingSessionCalendarReadRepository(Protocol):
    """Load a proven session calendar for a coverage window without mutation."""

    def load_calendar(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> KnownTradingSessionCalendar | None:
        """Return a proven calendar or None when coverage cannot be proven.

        Implementations must not create databases, tables, indexes, columns,
        directories, or files. Fail closed when the source cannot prove complete
        coverage for the requested interval.
        """
        ...
