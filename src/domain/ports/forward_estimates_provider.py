"""
Port: ForwardEstimatesProvider

Provides next-year analyst EPS and Revenue estimates for a ticker.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.forward_estimates import ForwardEstimates


class ForwardEstimatesProvider(ABC):
    """Abstract source for per-ticker analyst forward estimates."""

    @abstractmethod
    def get_forward_estimates(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> ForwardEstimates | None:
        """Return next-year analyst estimates for ticker.

        Args:
            ticker: Stock ticker symbol.
            as_of_date: When provided, only return a snapshot fetched on or
                before this historical date. None means current/live behavior.

        Returns:
            ForwardEstimates, or None if data unavailable.
            Never raises.
        """
        ...
