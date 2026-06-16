"""
Port: CorporateActionRepository

Provides upcoming ex-dividend (and other corporate action) dates for a ticker.
Implementations may source data from Stockbit Playwright session, a CSV file,
or any other provider — the application layer only depends on this interface.

Layer: Application (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date


class CorporateActionRepository(ABC):
    """Abstract source for corporate action dates."""

    @abstractmethod
    def get_upcoming_ex_dates(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[date]:
        """Return ex-dividend dates for ticker falling within [from_date, to_date].

        Returns an empty list if no ex-dates are found or if data is unavailable.
        Never raises — implementations must catch and swallow errors gracefully.
        """
        ...
