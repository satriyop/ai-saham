"""
Application use cases/workflows for fetching broker data commands.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date, timedelta

from src.application.use_case.fetch_broker_data_use_case import (
    FetchBrokerDataRequest,
    FetchBrokerDataResponse,
    FetchBrokerDataUseCase,
)
from src.domain.entities.broker_flow import ForeignFlowPoint, ForeignFlowSnapshot
from src.domain.ports.broker_data_provider import (
    BrokerDataProvider,
    BrokerDataProviderError,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class FetchBrokerSummaryWorkflowRequest:
    ticker: str
    start_date: date
    end_date: date
    days: int
    refresh: bool
    provider_name: str


@dataclass(frozen=True)
class FetchBrokerSummaryWorkflowResult:
    response: FetchBrokerDataResponse
    exact_flow_saved_count: int = 0


class FetchBrokerSummaryWorkflowUseCase:
    """Use case to fetch and cache broker summary, along with stockbit exact flow if needed."""

    def __init__(
        self,
        provider: BrokerDataProvider,
        repository: BrokerDataRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._fetch_use_case = FetchBrokerDataUseCase(provider, repository)

    def execute(
        self, request: FetchBrokerSummaryWorkflowRequest
    ) -> FetchBrokerSummaryWorkflowResult:
        response = self._fetch_use_case.execute(
            FetchBrokerDataRequest(
                ticker=request.ticker,
                start_date=request.start_date,
                end_date=request.end_date,
                refresh=request.refresh,
            )
        )

        exact_flow_saved_count = 0
        if not response.from_cache and request.provider_name == "stockbit":
            points = self._provider.fetch_foreign_flow_history(request.ticker, days=request.days)
            if points:
                self._repository.save_foreign_flow_points(points)
                exact_flow_saved_count = len(points)

        return FetchBrokerSummaryWorkflowResult(
            response=response,
            exact_flow_saved_count=exact_flow_saved_count,
        )


@dataclass(frozen=True)
class FetchForeignTopStocksWorkflowRequest:
    days: int
    limit: int
    save: bool
    today: date


@dataclass(frozen=True)
class FetchForeignTopStocksWorkflowResult:
    start_date: date
    end_date: date
    snapshots: list[ForeignFlowSnapshot]
    saved_count: int = 0
    save_warning: str | None = None


class FetchForeignTopStocksWorkflowUseCase:
    """Use case to fetch foreign top stocks scan and optionally save to repository."""

    def __init__(
        self,
        provider: BrokerDataProvider,
        repository: BrokerDataRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(
        self, request: FetchForeignTopStocksWorkflowRequest
    ) -> FetchForeignTopStocksWorkflowResult:
        if not self._provider.is_authenticated():
            raise BrokerDataProviderError("Not authenticated.")

        end_date = request.today
        start_date = end_date - timedelta(days=request.days)

        snapshots = self._provider.fetch_foreign_top_stocks(
            start_date, end_date, limit=request.limit
        )

        saved_count = 0
        save_warning = None

        if request.save and snapshots:
            try:
                self._repository.save_foreign_flow_snapshots(
                    snapshots,
                    snapshot_date=end_date,
                    period_days=request.days,
                )
                saved_count = len(snapshots)
            except Exception as e:
                save_warning = str(e)

        return FetchForeignTopStocksWorkflowResult(
            start_date=start_date,
            end_date=end_date,
            snapshots=snapshots,
            saved_count=saved_count,
            save_warning=save_warning,
        )


@dataclass(frozen=True)
class FetchBrokerFlowHistoryWorkflowRequest:
    ticker: str
    days: int


@dataclass(frozen=True)
class FetchBrokerFlowHistoryWorkflowResult:
    ticker: str
    points: list[ForeignFlowPoint]
    saved_count: int


class FetchBrokerFlowHistoryWorkflowUseCase:
    """Use case to fetch daily broker flow history (time-series) and save to repository."""

    def __init__(
        self,
        provider: BrokerDataProvider,
        repository: BrokerDataRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(
        self, request: FetchBrokerFlowHistoryWorkflowRequest
    ) -> FetchBrokerFlowHistoryWorkflowResult:
        if not self._provider.is_authenticated():
            raise BrokerDataProviderError("Not authenticated.")

        ticker_upper = request.ticker.upper()
        points = self._provider.fetch_foreign_flow_history(ticker_upper, days=request.days)

        saved_count = 0
        if points:
            self._repository.save_foreign_flow_points(points)
            saved_count = len(points)

        return FetchBrokerFlowHistoryWorkflowResult(
            ticker=ticker_upper,
            points=points,
            saved_count=saved_count,
        )
