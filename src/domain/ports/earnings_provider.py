"""
Port: EarningsProvider

Provides historical quarterly earnings (EPS actual vs estimate) for a ticker.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.earnings_record import EarningsRecord


class EarningsProvider(ABC):
    """Abstract source for per-ticker quarterly earnings history."""

    @abstractmethod
    def get_earnings_history(
        self,
        ticker: str,
        quarters: int = 4,
        as_of_date: date | None = None,
    ) -> list[EarningsRecord]:
        """Return up to `quarters` most recent earnings records, newest first.

        as_of_date=None keeps current/live behavior. Historical callers receive
        only cache rows fetched on or before as_of_date.

        Returns an empty list if data is unavailable.
        Never raises.
        """
        ...

    @abstractmethod
    def is_cache_fresh(self, ticker: str) -> bool:
        """Return True when the cached earnings history is still valid (7-day TTL)."""
        ...
