"""
BrokerDataRepository port - interface for persisting broker flow data.

This is a domain port (interface). Concrete implementations
live in infrastructure/persistence/.

Layer: Domain
Dependencies: None (only domain entities)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.broker_flow import BrokerSummary


class BrokerDataRepository(ABC):
    """
    Abstract interface for broker flow data persistence.

    Implementations may include:
    - SQLiteBrokerRepository (SQLite storage)
    - InMemoryBrokerRepository (for testing)

    The domain layer depends on this interface, never on concrete implementations.
    """

    @abstractmethod
    def save_broker_summary(self, summary: BrokerSummary) -> None:
        """
        Save a broker summary to the repository.

        Uses upsert semantics - updates if exists, inserts if new.

        Args:
            summary: BrokerSummary entity to persist.

        Raises:
            BrokerDataRepositoryError: If save fails.
        """
        pass

    @abstractmethod
    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        """
        Save multiple broker summaries to the repository.

        Uses upsert semantics for each summary.

        Args:
            summaries: List of BrokerSummary entities to persist.

        Raises:
            BrokerDataRepositoryError: If save fails.
        """
        pass

    @abstractmethod
    def get_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        """
        Retrieve a broker summary for a specific date.

        Args:
            ticker: Stock ticker symbol
            target_date: The trading date

        Returns:
            BrokerSummary if found, None otherwise.

        Raises:
            BrokerDataRepositoryError: If retrieval fails.
        """
        pass

    @abstractmethod
    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        """
        Retrieve broker summaries within a date range.

        Args:
            ticker: Stock ticker symbol
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            List of BrokerSummary entities, sorted by date ascending.

        Raises:
            BrokerDataRepositoryError: If retrieval fails.
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
        Check if repository has data for the specified range.

        Args:
            ticker: Stock ticker symbol
            start_date: Start of date range
            end_date: End of date range

        Returns:
            True if data exists covering the range, False otherwise.
        """
        pass

    @abstractmethod
    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        """
        Get the date range of stored data for a ticker.

        Returns:
            Tuple of (earliest_date, latest_date) or None if no data.
        """
        pass


class BrokerDataRepositoryError(Exception):
    """Raised when broker data repository encounters an error."""

    pass
