"""
FetchBrokerDailyFlowsUseCase — per-day per-broker flow fetcher.

Fetches real daily broker flow data from Stockbit (one record per trading
session per broker code) and caches it in broker_daily_flow table.

This is the accurate replacement for marketdetectors-based data, which
returns period aggregates masquerading as daily rows.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date, timedelta

from src.domain.entities.broker_flow import BrokerDailyFlow
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.broker_data_provider import BrokerDataProvider

TOLERANCE_DAYS = 7


@dataclass(frozen=True)
class FetchBrokerDailyFlowsRequest:
    ticker: str
    days: int = 365
    broker_codes: list[str] | None = None  # None = use provider default
    refresh: bool = False


@dataclass(frozen=True)
class FetchBrokerDailyFlowsResponse:
    ticker: str
    added_count: int       # new (date, broker_code) pairs stored
    fetched_count: int     # rows returned by the API call (0 if cached or unsupported)
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
        end_date = date.today()
        tolerated_end = end_date - timedelta(days=TOLERANCE_DAYS)

        if not hasattr(self._provider, "fetch_broker_daily_flows"):
            return FetchBrokerDailyFlowsResponse(
                ticker=ticker,
                added_count=0,
                fetched_count=0,
                cached_range=None,
                status="unsupported",
            )

        if not request.refresh:
            cached = self._repository.get_broker_daily_flow_date_range(ticker, source=source)
            if cached and cached[1] >= tolerated_end:
                return FetchBrokerDailyFlowsResponse(
                    ticker=ticker,
                    added_count=0,
                    fetched_count=0,
                    cached_range=cached,
                    status="cached",
                )

        before_range = self._repository.get_broker_daily_flow_date_range(ticker, source=source)
        before_dates: set[tuple[date, str]] = {
            (f.date, f.broker_code)
            for f in self._repository.get_broker_daily_flows(ticker, source=source)
        }

        flows = self._provider.fetch_broker_daily_flows(  # type: ignore[attr-defined]
            ticker=ticker,
            broker_codes=request.broker_codes,
            days=request.days,
        )

        if flows:
            self._repository.save_broker_daily_flows(flows)

        after_dates: set[tuple[date, str]] = {
            (f.date, f.broker_code)
            for f in self._repository.get_broker_daily_flows(ticker, source=source)
        }
        added_count = len(after_dates - before_dates)
        cached_range = self._repository.get_broker_daily_flow_date_range(ticker, source=source)

        if not flows and not before_range:
            return FetchBrokerDailyFlowsResponse(
                ticker=ticker,
                added_count=0,
                fetched_count=0,
                cached_range=None,
                status="no-data",
            )

        active_codes = len({f.broker_code for f in flows}) if flows else 0
        return FetchBrokerDailyFlowsResponse(
            ticker=ticker,
            added_count=added_count,
            fetched_count=len(flows) if flows else 0,
            cached_range=cached_range,
            status="fetched",
            active_codes=active_codes,
        )
