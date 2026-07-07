"""
Port: CompanyProfileProvider

Provides company profile data (background, IPO history, contacts) for a ticker.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.company_profile import CompanyProfile


class CompanyProfileProvider(ABC):
    """Abstract source for per-ticker company profile."""

    @abstractmethod
    def get_profile(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> CompanyProfile | None:
        """Return company profile for ticker.

        as_of_date=None keeps current/live behavior. Historical callers receive
        only snapshots fetched on or before as_of_date.

        Returns:
            CompanyProfile, or None if data unavailable.
            Never raises.
        """
        ...
