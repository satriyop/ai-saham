"""
Tests for Fetch Broker Command Workflows.

Layer: Application (Tests)
"""

from datetime import date
from decimal import Decimal
from typing import Optional

import pytest

from src.application.use_case.fetch_broker_command_workflows import (
    FetchBrokerFlowHistoryWorkflowRequest,
    FetchBrokerFlowHistoryWorkflowUseCase,
    FetchBrokerSummaryWorkflowRequest,
    FetchBrokerSummaryWorkflowUseCase,
    FetchForeignTopStocksWorkflowRequest,
    FetchForeignTopStocksWorkflowUseCase,
)
from src.domain.entities.broker_flow import (
    BrokerSummary,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataProvider,
    BrokerDataProviderError,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository


class FakeBrokerDataProvider(BrokerDataProvider):
    def __init__(self, provider_name: str = "idx", authenticated: bool = True) -> None:
        self._provider_name = provider_name
        self._authenticated = authenticated
        self.summaries_fetched = 0
        self.snapshots_fetched = 0
        self.history_fetched = 0
        self.top_stocks: list[ForeignFlowSnapshot] = []
        self.flow_history: list[ForeignFlowPoint] = []
        self.last_fetched_ticker: Optional[str] = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def is_authenticated(self) -> bool:
        return self._authenticated

    def fetch_broker_summary(
        self, ticker: str, target_date: date
    ) -> Optional[BrokerSummary]:
        self.summaries_fetched += 1
        self.last_fetched_ticker = ticker
        return BrokerSummary(
            ticker=ticker,
            date=target_date,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("100"),
            foreign_sell_value=Decimal("50"),
            foreign_buy_lot=10,
            foreign_sell_lot=5,
            total_value=Decimal("1000"),
            total_lot=100,
            source=self._provider_name,
        )

    def fetch_broker_summaries(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[BrokerSummary]:
        self.summaries_fetched += 1
        self.last_fetched_ticker = ticker
        return [
            BrokerSummary(
                ticker=ticker,
                date=start_date,
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("100"),
                foreign_sell_value=Decimal("50"),
                foreign_buy_lot=10,
                foreign_sell_lot=5,
                total_value=Decimal("1000"),
                total_lot=100,
                source=self._provider_name,
            )
        ]

    def fetch_foreign_top_stocks(
        self, start_date: date, end_date: date, limit: int = 20
    ) -> list[ForeignFlowSnapshot]:
        self.snapshots_fetched += 1
        return self.top_stocks

    def fetch_foreign_flow_history(
        self, ticker: str, days: int = 365
    ) -> list[ForeignFlowPoint]:
        self.history_fetched += 1
        self.last_fetched_ticker = ticker
        return self.flow_history


class FakeBrokerDataRepository(BrokerDataRepository):
    def __init__(self, raise_on_save: bool = False, initially_cached: bool = False) -> None:
        self.saved_summaries: list[BrokerSummary] = []
        self.saved_points: list[ForeignFlowPoint] = []
        self.saved_snapshots: list[
            tuple[list[ForeignFlowSnapshot], date, int]
        ] = []
        self.raise_on_save = raise_on_save
        self.initially_cached = initially_cached

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self.saved_summaries.append(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self.saved_summaries.extend(summaries)

    def get_broker_summary(
        self, ticker: str, target_date: date
    ) -> Optional[BrokerSummary]:
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        source: Optional[str] = None,
    ) -> list[BrokerSummary]:
        if self.initially_cached:
            return [
                BrokerSummary(
                    ticker=ticker,
                    date=start_date or date.today(),
                    top_buyers=(),
                    top_sellers=(),
                    foreign_buy_value=Decimal("100"),
                    foreign_sell_value=Decimal("50"),
                    foreign_buy_lot=10,
                    foreign_sell_lot=5,
                    total_value=Decimal("1000"),
                    total_lot=100,
                    source=source or "idx",
                )
            ]
        return []

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        source: Optional[str] = None,
    ) -> bool:
        return self.initially_cached

    def get_date_range(
        self, ticker: str, source: Optional[str] = None
    ) -> Optional[tuple[date, date]]:
        return None

    def save_foreign_flow_points(self, points: list[ForeignFlowPoint]) -> None:
        if self.raise_on_save:
            raise Exception("Save failed")
        self.saved_points.extend(points)

    def save_foreign_flow_snapshots(
        self,
        snapshots: list[ForeignFlowSnapshot],
        snapshot_date: date,
        period_days: int,
    ) -> None:
        if self.raise_on_save:
            raise Exception("Save failed")
        self.saved_snapshots.append((snapshots, snapshot_date, period_days))


def test_summary_workflow_calls_fetch_broker_data_use_case() -> None:
    # 1. Summary workflow calls FetchBrokerDataUseCase.
    provider = FakeBrokerDataProvider(provider_name="idx")
    repository = FakeBrokerDataRepository(initially_cached=False)
    use_case = FetchBrokerSummaryWorkflowUseCase(provider, repository)

    request = FetchBrokerSummaryWorkflowRequest(
        ticker="BBCA",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        days=5,
        refresh=False,
        provider_name="idx",
    )
    result = use_case.execute(request)

    assert provider.summaries_fetched == 1
    assert result.response.from_cache is False
    assert len(result.response.summaries) == 1


def test_summary_workflow_saves_exact_flow_only_when_stockbit_and_not_cache() -> None:
    # 2. Summary workflow saves exact flow only when provider is stockbit and response is not cache.
    provider = FakeBrokerDataProvider(provider_name="stockbit")
    provider.flow_history = [
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2024, 1, 1),
            net_val=Decimal("100"),
            net_lot=10,
            avg_price=Decimal("10"),
            source="stockbit",
        )
    ]
    repository = FakeBrokerDataRepository(initially_cached=False)
    use_case = FetchBrokerSummaryWorkflowUseCase(provider, repository)

    request = FetchBrokerSummaryWorkflowRequest(
        ticker="BBCA",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        days=5,
        refresh=False,
        provider_name="stockbit",
    )
    result = use_case.execute(request)

    assert result.exact_flow_saved_count == 1
    assert len(repository.saved_points) == 2  # 1 from FetchBrokerDataUseCase, 1 from exact flow


def test_summary_workflow_does_not_save_exact_flow_when_cache() -> None:
    # 3. Summary workflow does not save exact flow when response.from_cache=True.
    provider = FakeBrokerDataProvider(provider_name="stockbit")
    repository = FakeBrokerDataRepository(initially_cached=True)
    use_case = FetchBrokerSummaryWorkflowUseCase(provider, repository)

    request = FetchBrokerSummaryWorkflowRequest(
        ticker="BBCA",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        days=5,
        refresh=False,
        provider_name="stockbit",
    )
    result = use_case.execute(request)

    assert result.response.from_cache is True
    assert result.exact_flow_saved_count == 0
    assert len(repository.saved_points) == 0


def test_top_foreign_workflow_fetches_and_saves() -> None:
    # 4. Top-foreign workflow fetches provider snapshots and saves unless save=False.
    provider = FakeBrokerDataProvider(provider_name="stockbit")
    provider.top_stocks = [
        ForeignFlowSnapshot(
            ticker="BBCA",
            date=date(2024, 1, 5),
            net_val=Decimal("1000"),
            net_lot=100,
        )
    ]
    repository = FakeBrokerDataRepository()
    use_case = FetchForeignTopStocksWorkflowUseCase(provider, repository)

    # Test with save=True
    request_save = FetchForeignTopStocksWorkflowRequest(
        days=7,
        limit=20,
        save=True,
        today=date(2024, 1, 5),
    )
    result_save = use_case.execute(request_save)

    assert provider.snapshots_fetched == 1
    assert result_save.saved_count == 1
    assert len(repository.saved_snapshots) == 1

    # Test with save=False
    request_no_save = FetchForeignTopStocksWorkflowRequest(
        days=7,
        limit=20,
        save=False,
        today=date(2024, 1, 5),
    )
    result_no_save = use_case.execute(request_no_save)

    assert provider.snapshots_fetched == 2
    assert result_no_save.saved_count == 0
    assert len(repository.saved_snapshots) == 1  # Should not increase


def test_top_foreign_save_failure_returns_warning() -> None:
    # 5. Top-foreign save failure returns warning and does not raise.
    provider = FakeBrokerDataProvider(provider_name="stockbit")
    provider.top_stocks = [
        ForeignFlowSnapshot(
            ticker="BBCA",
            date=date(2024, 1, 5),
            net_val=Decimal("1000"),
            net_lot=100,
        )
    ]
    repository = FakeBrokerDataRepository(raise_on_save=True)
    use_case = FetchForeignTopStocksWorkflowUseCase(provider, repository)

    request = FetchForeignTopStocksWorkflowRequest(
        days=7,
        limit=20,
        save=True,
        today=date(2024, 1, 5),
    )
    result = use_case.execute(request)

    assert result.saved_count == 0
    assert result.save_warning == "Save failed"


def test_top_foreign_unauthenticated_raises() -> None:
    # 6. Top-foreign unauthenticated provider raises BrokerDataProviderError("Not authenticated.").
    provider = FakeBrokerDataProvider(provider_name="stockbit", authenticated=False)
    repository = FakeBrokerDataRepository()
    use_case = FetchForeignTopStocksWorkflowUseCase(provider, repository)

    request = FetchForeignTopStocksWorkflowRequest(
        days=7,
        limit=20,
        save=True,
        today=date(2024, 1, 5),
    )

    with pytest.raises(BrokerDataProviderError) as exc:
        use_case.execute(request)

    assert "Not authenticated." in str(exc.value)


def test_broker_history_workflow_fetches_saves_uppercases() -> None:
    # 7. Broker-history workflow fetches, saves, uppercases ticker.
    provider = FakeBrokerDataProvider(provider_name="stockbit")
    provider.flow_history = [
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2024, 1, 1),
            net_val=Decimal("100"),
            net_lot=10,
            avg_price=Decimal("10"),
            source="stockbit",
        )
    ]
    repository = FakeBrokerDataRepository()
    use_case = FetchBrokerFlowHistoryWorkflowUseCase(provider, repository)

    request = FetchBrokerFlowHistoryWorkflowRequest(
        ticker="bbca",
        days=30,
    )
    result = use_case.execute(request)

    assert provider.last_fetched_ticker == "BBCA"
    assert result.ticker == "BBCA"
    assert result.saved_count == 1
    assert len(repository.saved_points) == 1


def test_broker_history_no_points() -> None:
    # 8. Broker-history no points returns saved count 0.
    provider = FakeBrokerDataProvider(provider_name="stockbit")
    provider.flow_history = []
    repository = FakeBrokerDataRepository()
    use_case = FetchBrokerFlowHistoryWorkflowUseCase(provider, repository)

    request = FetchBrokerFlowHistoryWorkflowRequest(
        ticker="BBCA",
        days=30,
    )
    result = use_case.execute(request)

    assert result.saved_count == 0
    assert len(repository.saved_points) == 0


def test_broker_history_unauthenticated_raises() -> None:
    # 9. Broker-history unauthenticated provider raises.
    provider = FakeBrokerDataProvider(provider_name="stockbit", authenticated=False)
    repository = FakeBrokerDataRepository()
    use_case = FetchBrokerFlowHistoryWorkflowUseCase(provider, repository)

    request = FetchBrokerFlowHistoryWorkflowRequest(
        ticker="BBCA",
        days=30,
    )

    with pytest.raises(BrokerDataProviderError) as exc:
        use_case.execute(request)

    assert "Not authenticated." in str(exc.value)
