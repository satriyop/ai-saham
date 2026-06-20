"""
Port: ForwardEstimatesProvider

Provides next-year analyst EPS and Revenue estimates for a ticker.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.forward_estimates import ForwardEstimates


class ForwardEstimatesProvider(ABC):
    """Abstract source for per-ticker analyst forward estimates."""

    @abstractmethod
    def get_forward_estimates(self, ticker: str) -> ForwardEstimates | None:
        """Return next-year analyst estimates for ticker.

        Returns:
            ForwardEstimates, or None if data unavailable.
            Never raises.
        """
        ...
