"""
FetchBrokerDailyFlowsUseCase — per-day per-broker flow fetcher.

Fetches real daily broker flow data from Stockbit (one record per trading
session per broker code) and caches it in broker_daily_flow table.

This is the accurate replacement for marketdetectors-based data, which
returns period aggregates masquerading as daily rows.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date

from src.domain.ports.broker_data_provider import BrokerDataProvider
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class FetchBrokerDailyFlowsRequest:
    ticker: str
    days: int = 365
    broker_codes: list[str] | None = None  # None = use provider default
    refresh: bool = False
    expected_latest_date: date | None = None


@dataclass(frozen=True)
class FetchBrokerDailyFlowsResponse:
    ticker: str
    added_count: int       # new (date, broker_code) pairs stored
    fetched_count: int     # rows actually saved (0 if cached or unsupported)
    cached_range: tuple[date, date] | None
    status: str            # 'fetched' | 'cached' | 'no-data' | 'unsupported'
    active_codes: int = 0  # distinct broker codes in the fetched batch


class FetchBrokerDailyFlowsUseCase:
    """
    Cache-aware fetcher for per-day per-broker flow data.

    Flow:
      1. Check if broker_daily_flow has recent enough data for this source.
      2. If cached and current → return 'cached'.
      3. Otherwise call provider.fetch_broker_daily_flows() and persist.
      4. Track how many new rows were added.
    """

    def __init__(
        self,
        provider: BrokerDataProvider,
        repository: BrokerDataRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(self, request: FetchBrokerDailyFlowsRequest) -> FetchBrokerDailyFlowsResponse:
        ticker = request.ticker.upper()
        source = self._provider.provider_name
        expected_latest = request.expected_latest_date or date.today()

        if not hasattr(self._provider, "fetch_broker_daily_flows"):
            return FetchBrokerDailyFlowsResponse(
                ticker=ticker,
                added_count=0,
                fetched_count=0,
                cached_range=None,
                status="unsupported",
            )

        # Single DB call serves both the freshness check and the before_max_date anchor.
        before_range = self._repository.get_broker_daily_flow_date_range(ticker, source=source)
        if not request.refresh:
            if before_range and before_range[1] >= expected_latest:
                return FetchBrokerDailyFlowsResponse(
                    ticker=ticker,
                    added_count=0,
                    fetched_count=0,
                    cached_range=before_range,
                    status="cached",
                )

        before_max_date = before_range[1] if before_range else None

        flows = self._provider.fetch_broker_daily_flows(  # type: ignore[attr-defined]
            ticker=ticker,
            broker_codes=request.broker_codes,
            days=request.days,
        )

        if not flows and not before_range:
            return FetchBrokerDailyFlowsResponse(
                ticker=ticker,
                added_count=0,
                fetched_count=0,
                cached_range=None,
                status="no-data",
            )

        # Save all on first fetch; otherwise only append rows newer than what we have.
        if before_max_date is None:
            new_flows = flows or []
        else:
            new_flows = [f for f in flows if f.date > before_max_date] if flows else []

        if new_flows:
            self._repository.save_broker_daily_flows(new_flows)
            cached_range = self._repository.get_broker_daily_flow_date_range(ticker, source=source)
        else:
            cached_range = before_range

        added_count = len(new_flows)
        active_codes = len({f.broker_code for f in new_flows}) if new_flows else 0

        return FetchBrokerDailyFlowsResponse(
            ticker=ticker,
            added_count=added_count,
            fetched_count=len(new_flows),
            cached_range=cached_range,
            status="fetched",
            active_codes=active_codes,
        )
