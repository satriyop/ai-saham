"""
Port: SeasonalityProvider

Provides monthly seasonality statistics for a ticker.
Implementations may source data from Stockbit or any other provider.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.seasonal_edge import SeasonalEdge


class SeasonalityProvider(ABC):
    """Abstract source for monthly seasonality data."""

    @abstractmethod
    def get_seasonal_edge(
        self,
        ticker: str,
        year: int,
        month: int,
        back_years: int = 5,
    ) -> SeasonalEdge | None:
        """Return seasonality statistics for ticker in the given calendar month.

        Args:
            ticker:     IDX ticker symbol.
            year:       Reference year (used as the end year for history lookup).
            month:      Calendar month to retrieve (1=Jan … 12=Dec).
            back_years: Number of historical years to include.

        Returns:
            SeasonalEdge if data is available, None otherwise.
            Never raises — implementations must catch errors gracefully.
        """
        ...
