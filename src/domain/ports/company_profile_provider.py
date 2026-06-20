"""
Port: CompanyProfileProvider

Provides company profile data (background, IPO history, contacts) for a ticker.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.company_profile import CompanyProfile


class CompanyProfileProvider(ABC):
    """Abstract source for per-ticker company profile."""

    @abstractmethod
    def get_profile(self, ticker: str) -> CompanyProfile | None:
        """Return company profile for ticker.

        Returns:
            CompanyProfile, or None if data unavailable.
            Never raises.
        """
        ...
