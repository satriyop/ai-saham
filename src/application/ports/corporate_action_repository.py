"""
Port: CorporateActionRepository

Provides upcoming corporate action events (dividend, rights issue, RUPS, etc.)
for a ticker. Implementations may source data from Stockbit or any other provider.

Layer: Application (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.corporate_action_event import CorporateActionEvent


class CorporateActionRepository(ABC):
    """Abstract source for upcoming corporate actions."""

    @abstractmethod
    def get_upcoming_events(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[CorporateActionEvent]:
        """Return corporate action events for ticker with an ex/cum/record date
        in [from_date, to_date].

        Returns an empty list when no events are found or data is unavailable.
        Never raises — implementations must catch and log errors gracefully.
        """
        ...

    def get_upcoming_ex_dates(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[date]:
        """Return ex-dividend dates falling within [from_date, to_date].

        Convenience wrapper over get_upcoming_events() — kept for backward
        compatibility with existing call-sites that only care about dividends.
        """
        events = self.get_upcoming_events(ticker, from_date, to_date)
        return [e.ex_date for e in events if e.is_dividend and e.ex_date is not None]
