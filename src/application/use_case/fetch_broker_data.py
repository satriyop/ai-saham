"""
Fetch Broker Data Use Case.

Orchestrates fetching broker summary data from provider
and caching it locally.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.domain.entities.broker_flow import BrokerSummary, ForeignFlowPoint
from src.domain.ports.broker_data_provider import (
    BrokerDataProvider,
    BrokerDataProviderError,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class FetchBrokerDataRequest:
    """Request to fetch broker data."""

    ticker: str
    start_date: date
    end_date: date
    refresh: bool = False  # Force refresh even if cached


@dataclass(frozen=True)
class FetchBrokerDataResponse:
    """Response containing fetched broker data."""

    ticker: str
    summaries: list[BrokerSummary]
    from_cache: bool
    message: str


class FetchBrokerDataUseCase:
    """
    Use case for fetching and caching broker data.

    Flow:
    1. Check if data exists in local repository
    2. If not cached (or refresh=True), fetch from provider
    3. Save to local repository
    4. Return broker summaries
    """

    def __init__(
        self,
        provider: BrokerDataProvider,
        repository: BrokerDataRepository,
    ) -> None:
        """
        Initialize use case.

        Args:
            provider: Broker data provider (e.g., Stockbit)
            repository: Local repository for caching
        """
        self._provider = provider
        self._repository = repository

    def execute(self, request: FetchBrokerDataRequest) -> FetchBrokerDataResponse:
        """
        Execute the fetch broker data use case.

        Args:
            request: FetchBrokerDataRequest with ticker and date range

        Returns:
            FetchBrokerDataResponse with broker summaries

        Raises:
            BrokerDataProviderError: If fetch fails
        """
        ticker = request.ticker.upper()
        source = self._provider.provider_name

        # Check if we need to fetch from provider
        if not request.refresh:
            if self._repository.has_data(
                ticker, request.start_date, request.end_date, source=source
            ):
                summaries = self._repository.get_broker_summaries(
                    ticker,
                    request.start_date,
                    request.end_date,
                    source=source,
                )
                return FetchBrokerDataResponse(
                    ticker=ticker,
                    summaries=summaries,
                    from_cache=True,
                    message=f"Loaded {len(summaries)} days from cache ({source})",
                )

        # Check authentication
        if not self._provider.is_authenticated():
            raise BrokerDataProviderError(
                "Broker provider is not authenticated. "
                "For Stockbit session data, run 'saham fetch stockbit login'."
            )

        # Fetch from provider
        summaries = self._provider.fetch_broker_summaries(
            ticker,
            request.start_date,
            request.end_date,
        )

        # Save summaries and derive aggregate flow points for time-series queries
        if summaries:
            self._repository.save_broker_summaries(summaries)
            flow_points = [
                ForeignFlowPoint(
                    ticker=s.ticker,
                    date=s.date,
                    net_val=s.foreign_net_value,
                    net_lot=s.foreign_net_lot,
                    avg_price=Decimal("0"),
                    source=source,
                )
                for s in summaries
            ]
            self._repository.save_foreign_flow_points(flow_points)

        return FetchBrokerDataResponse(
            ticker=ticker,
            summaries=summaries,
            from_cache=False,
            message=f"Fetched {len(summaries)} days from {source}",
        )


class GetBrokerDataUseCase:
    """
    Use case for getting broker data from local repository only.

    Does not fetch from provider - only returns cached data.
    Useful for indicators and backtesting where data should be pre-loaded.
    """

    def __init__(self, repository: BrokerDataRepository) -> None:
        """
        Initialize use case.

        Args:
            repository: Local repository for broker data
        """
        self._repository = repository

    def execute(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        """
        Get broker summaries from local repository.

        Args:
            ticker: Stock ticker symbol
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            List of BrokerSummary entities from cache
        """
        return self._repository.get_broker_summaries(
            ticker.upper(),
            start_date,
            end_date,
        )
