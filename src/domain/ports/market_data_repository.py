"""
MarketDataRepository port - interface for caching market data.

This is a domain port (interface). Concrete implementations
live in infrastructure/persistence/.
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.candle import Candle


class MarketDataRepository(ABC):
    """
    Abstract interface for market data persistence/cache.

    Implementations may include:
    - SQLiteMarketRepository
    - DuckDBMarketRepository
    - InMemoryMarketRepository (for testing)

    The domain layer depends on this interface, never on concrete storage.
    """

    @abstractmethod
    def save_candles(self, candles: list[Candle]) -> None:
        """
        Save candles to storage. Upserts if data exists.

        Args:
            candles: List of Candle entities to persist.

        Raises:
            MarketDataRepositoryError: If save fails.
        """
        pass

    @abstractmethod
    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        """
        Retrieve candles from storage.

        Args:
            ticker: Stock ticker symbol
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            List of Candle entities, sorted by date ascending.
            Empty list if no data found.

        Raises:
            MarketDataRepositoryError: If retrieval fails.
        """
        pass

    @abstractmethod
    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> bool:
        """
        Check if cache has data for the specified ticker and date range.

        Args:
            ticker: Stock ticker symbol
            start_date: Start of date range
            end_date: End of date range

        Returns:
            True if cache contains data covering the full range.
        """
        pass

    @abstractmethod
    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        """
        Get the date range of cached data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (earliest_date, latest_date) or None if no data.
        """
        pass

    @abstractmethod
    def list_tickers_with_candles_between(
        self,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """
        Return distinct tickers that have at least one candle in
        ``[start_date, end_date]`` (inclusive), sorted ascending.

        Calendar-agnostic: callers map trading-session windows to calendar
        dates before calling. Empty list when none match.

        Raises:
            MarketDataRepositoryError: If the query fails.
        """
        pass


class MarketDataRepositoryError(Exception):
    """Raised when market data repository encounters an error."""

    pass
