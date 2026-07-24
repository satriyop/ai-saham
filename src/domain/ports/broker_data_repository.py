"""
BrokerDataRepository port - interface for persisting broker flow data.

This is a domain port (interface). Concrete implementations
live in infrastructure/persistence/.

Layer: Domain
Dependencies: None (only domain entities)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)


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
        source: str | None = None,
    ) -> list[BrokerSummary]:
        """
        Retrieve broker summaries within a date range.

        Args:
            ticker: Stock ticker symbol
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)
            source: Filter by source ('idx', 'stockbit'). None = best per date
                    (Stockbit preferred over IDX — 'stockbit' > 'idx' lexicographically).

        Returns:
            List of BrokerSummary entities, one per date, sorted by date ascending.

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
        source: str | None = None,
    ) -> bool:
        """
        Check if repository has data for the specified range.

        Args:
            ticker: Stock ticker symbol
            start_date: Start of date range
            end_date: End of date range
            source: Check only for this source. None = any source.

        Returns:
            True if data exists covering the range, False otherwise.
        """
        pass

    @abstractmethod
    def get_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        """
        Get the date range of stored data for a ticker.

        Args:
            source: Restrict to this source. None = any source.

        Returns:
            Tuple of (earliest_date, latest_date) or None if no data.
        """
        pass

    def get_cached_tickers(self) -> list[str]:
        """
        Retrieve a list of all tickers that have cached broker summary data.

        Returns:
            Sorted list of ticker symbols.
        """
        return []

    # ── Optional capabilities (non-abstract — providers that don't support ──
    # ── these return empty/no-op defaults)                                  ──

    def save_foreign_flow_points(self, points: list[ForeignFlowPoint]) -> None:
        """
        Save daily foreign broker flow time-series points.

        Each point has a source tag ('idx' or 'stockbit'). Both sources can
        coexist for the same (ticker, date) — they are not overwritten.
        IDX avg_price is approximate (close price); Stockbit is exact.
        """

    def get_foreign_flow_points(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[ForeignFlowPoint]:
        """
        Retrieve daily aggregate foreign flow points for a ticker.

        source=None returns the best per date (Stockbit preferred).
        source='idx' or 'stockbit' returns only that source.
        """
        return []

    def get_foreign_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        """
        Get the date range of stored aggregate foreign flow points.

        source=None returns any source. source='idx' or 'stockbit' restricts
        the range to that source.
        """
        return None

    def save_broker_daily_flows(self, flows: list[BrokerDailyFlow]) -> None:
        """
        Persist real per-day per-broker flow records.

        PK is (ticker, date, broker_code, source) — one row per trading session
        per broker. Never aggregates. Upserts on conflict.
        """

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        broker_codes: list[str] | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        """
        Retrieve per-broker daily flow records for a ticker.

        broker_codes=None returns all tracked broker codes.
        source=None returns all sources.
        Results sorted by (date, broker_code) ascending.

        Note on Imbalance: Summing net flows across all returned records for a
        particular date will result in a non-zero imbalance. This is expected
        because the repository only tracks select high-volume/institutional
        desks rather than the entire broker universe.
        """
        return []

    def get_broker_daily_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        """
        Get the earliest and latest date stored in broker_daily_flow for a ticker.

        source=None returns range across all sources.
        """
        return None

    def get_broker_daily_flows_by_code(
        self,
        broker_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        ticker: str | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        """
        Retrieve per-day flow rows for one tracked broker across tickers.

        desk-centric read of broker_daily_flow. Results sorted by
        (date ASC, ticker ASC). Empty list when none cached.
        """
        return []

    def save_foreign_flow_snapshots(
        self,
        snapshots: list[ForeignFlowSnapshot],
        snapshot_date: date,
        period_days: int,
    ) -> None:
        """
        Persist the result of a broker-centric universe scan.

        snapshot_date: when the scan was run.
        period_days: look-back window (1/3/7/30/90/365).
        Upserts — re-running the same scan on the same date replaces prior results.
        """

    def get_foreign_flow_snapshots(
        self,
        snapshot_date: date,
        period_days: int,
    ) -> list[ForeignFlowSnapshot]:
        """Return universe scan results for a specific date and period window."""
        return []


class BrokerDataRepositoryError(Exception):
    """Raised when broker data repository encounters an error."""

    pass
