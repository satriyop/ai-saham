"""
MarketDataProvider port - interface for fetching market data.

This is a domain port (interface). Concrete implementations
live in infrastructure/data_providers/.
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.candle import Candle


class MarketDataProvider(ABC):
    """
    Abstract interface for market data providers.

    Implementations may include:
    - YahooFinanceProvider (yfinance)
    - IDXProvider (official IDX data)
    - CSVProvider (local CSV files)

    The domain layer depends on this interface, never on concrete providers.
    """

    @abstractmethod
    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        """
        Fetch daily OHLCV data for a ticker within a date range.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA' for IDX)
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of Candle entities, sorted by date ascending.
            Empty list if no data available.

        Raises:
            MarketDataProviderError: If fetch fails due to network or provider issues.
        """
        pass


class MarketDataProviderError(Exception):
    """Raised when market data provider encounters an error."""

    pass
