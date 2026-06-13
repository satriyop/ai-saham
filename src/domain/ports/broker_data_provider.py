"""
BrokerDataProvider port - interface for fetching broker flow data.

This is a domain port (interface). Concrete implementations
live in infrastructure/data_providers/.

Layer: Domain
Dependencies: None (only domain entities)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.broker_flow import BrokerFlowPoint, BrokerSummary, ForeignFlowSnapshot


class BrokerDataProvider(ABC):
    """
    Abstract interface for broker flow data providers.

    Implementations may include:
    - StockbitProvider (Stockbit API)
    - CSVBrokerProvider (local CSV files)

    The domain layer depends on this interface, never on concrete providers.
    """

    @abstractmethod
    def fetch_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        """
        Fetch broker summary for a ticker on a specific date.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA' for IDX)
            target_date: The trading date to fetch

        Returns:
            BrokerSummary if data available, None if no data for that date.

        Raises:
            BrokerDataProviderError: If fetch fails due to network or provider issues.
        """
        pass

    @abstractmethod
    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        """
        Fetch broker summaries for a ticker within a date range.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA' for IDX)
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of BrokerSummary entities, sorted by date ascending.
            Empty list if no data available.

        Raises:
            BrokerDataProviderError: If fetch fails due to network or provider issues.
        """
        pass

    @abstractmethod
    def is_authenticated(self) -> bool:
        """
        Check if provider is authenticated and ready to fetch data.

        Returns:
            True if authenticated, False otherwise.
        """
        pass

    def fetch_foreign_top_stocks(
        self,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ) -> list[ForeignFlowSnapshot]:
        """
        Return stocks that foreign brokers are most actively trading in the period.

        Broker-centric scan: given the set of known foreign brokers, which stocks
        appear in their top buys/sells? Useful for universe screening.

        Default: returns empty list (providers that don't support it are no-ops).
        """
        return []

    def fetch_broker_flow_history(
        self,
        ticker: str,
        days: int = 365,
    ) -> list[BrokerFlowPoint]:
        """
        Return daily aggregate foreign broker flow for a stock, up to `days` back.

        Stock-centric historical time-series: N.Val, N.Lot, Avg.Price per day.
        Used for backfilling and trend context.

        Default: returns empty list (providers that don't support it are no-ops).
        """
        return []


class BrokerDataProviderError(Exception):
    """Raised when broker data provider encounters an error."""

    pass


class BrokerDataAuthError(BrokerDataProviderError):
    """Raised when authentication fails or token is invalid/expired."""

    pass
