"""
Refresh broker data use case.

Owns deterministic broker refresh policy:
- independent IDX summary vs selected-source flow coverage
- older backfill vs forward-fill decisions for IDX summaries
- per-broker daily flow refresh when the provider supports it
- persisted-row status metadata

Layer: Application
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from src.application.use_case.fetch_broker_daily_flows import (
    FetchBrokerDailyFlowsRequest,
    FetchBrokerDailyFlowsResponse,
    FetchBrokerDailyFlowsUseCase,
)
from src.application.use_case.fetch_broker_data import (
    FetchBrokerDataRequest,
    FetchBrokerDataUseCase,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProvider,
    BrokerDataProviderError,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.ticker_notation_repository import TickerNotationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshBrokerDataRequest:
    ticker: str
    days: int
    refresh: bool = False
    end_date: date | None = None
    last_trading_day: date | None = None
    requested_start_tolerance_days: int = 7


@dataclass(frozen=True)
class RefreshBrokerDataResponse:
    ticker: str
    summaries_status: str
    flow_status: str
    notes: tuple[str, ...] = ()


class RefreshBrokerDataUseCase:
    """Refresh broker summaries and foreign-flow streams independently."""

    def __init__(
        self,
        broker_provider: BrokerDataProvider,
        idx_summary_provider: BrokerDataProvider,
        repository: BrokerDataRepository,
        notation_repository: TickerNotationRepository | None = None,
    ) -> None:
        self._broker_provider = broker_provider
        self._idx_summary_provider = idx_summary_provider
        self._repository = repository
        self._notation_repository = notation_repository

    def execute(self, request: RefreshBrokerDataRequest) -> RefreshBrokerDataResponse:
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")
        if request.days < 1:
            raise ValueError("Days must be at least 1")
        if ticker.startswith("^"):
            return RefreshBrokerDataResponse(ticker, "n/a:index", "n/a:index")

        if self._notation_repository is not None:
            notation = self._notation_repository.get_notation(ticker)
            if notation is not None and notation.tradeable is False:
                logger.info("Skipping broker fetch for %s — tradeable=False (suspended)", ticker)
                return RefreshBrokerDataResponse(ticker, "skip:suspended", "skip:suspended")

        end_date = request.end_date or date.today()
        requested_start = end_date - timedelta(days=request.days)
        last_trading = request.last_trading_day or end_date
        source = self._broker_provider.provider_name
        notes: list[str] = []

        daily_resp = self._refresh_daily_flow(ticker, request, notes)
        summary_fetch_ranges, previous_summary_latest = self._summary_fetch_ranges(
            ticker,
            requested_start,
            end_date,
            last_trading,
            request,
            notes,
        )
        previous_flow_latest = self._previous_flow_latest(ticker, source)

        before_flow_dates = {
            p.date for p in self._repository.get_foreign_flow_points(ticker, source=source)
        }
        before_summary_dates = {
            s.date for s in self._repository.get_broker_summaries(ticker, source="idx")
        }

        fetch_modes: set[str] = set()
        try:
            summary_uc = FetchBrokerDataUseCase(self._idx_summary_provider, self._repository)
            for start_date, fetch_end_date, fetch_mode in summary_fetch_ranges:
                if start_date > fetch_end_date:
                    continue
                fetch_modes.add(fetch_mode)
                summary_uc.execute(
                    FetchBrokerDataRequest(
                        ticker=ticker,
                        start_date=start_date,
                        end_date=fetch_end_date,
                        refresh=request.refresh,
                    )
                )

            self._refresh_foreign_flow_history(ticker, request.days, notes)

            after_flow_dates = {
                p.date for p in self._repository.get_foreign_flow_points(ticker, source=source)
            }
            after_summary_dates = {
                s.date for s in self._repository.get_broker_summaries(ticker, source="idx")
            }
            added_flow_count = len(after_flow_dates - before_flow_dates)
            added_summary_count = len(after_summary_dates - before_summary_dates)

            updated_summ_range = self._repository.get_date_range(ticker, source="idx")
            updated_flow_range = self._repository.get_foreign_flow_date_range(ticker, source=source)

            summaries_status = self._summary_status(
                added_summary_count,
                updated_summ_range,
                fetch_modes,
                summary_fetch_ranges,
                previous_summary_latest,
            )
            flow_status = self._flow_status(
                daily_resp=daily_resp,
                added_flow_count=added_flow_count,
                updated_flow_range=updated_flow_range,
                fetch_modes=fetch_modes,
                latest_date=updated_flow_range[1] if updated_flow_range else previous_flow_latest,
                previous_flow_latest=previous_flow_latest,
                last_trading=last_trading,
                refresh=request.refresh,
            )
            return RefreshBrokerDataResponse(
                ticker=ticker,
                summaries_status=summaries_status,
                flow_status=flow_status,
                notes=tuple(notes),
            )
        except BrokerDataAuthError:
            return RefreshBrokerDataResponse(ticker, "ERR:auth", "ERR:auth", tuple(notes))
        except BrokerDataProviderError as e:
            err = f"ERR:{str(e)[:30]}"
            return RefreshBrokerDataResponse(ticker, err, err, tuple(notes))
        except Exception as e:
            err = f"ERR:{str(e)[:30]}"
            return RefreshBrokerDataResponse(ticker, err, err, tuple(notes))

    def _refresh_daily_flow(
        self,
        ticker: str,
        request: RefreshBrokerDataRequest,
        notes: list[str],
    ) -> FetchBrokerDailyFlowsResponse | None:
        if not hasattr(self._broker_provider, "fetch_broker_daily_flows"):
            return None
        try:
            daily_uc = FetchBrokerDailyFlowsUseCase(self._broker_provider, self._repository)
            return daily_uc.execute(
                FetchBrokerDailyFlowsRequest(
                    ticker=ticker,
                    days=request.days,
                    refresh=request.refresh,
                    expected_latest_date=request.last_trading_day,
                )
            )
        except Exception as e:
            notes.append(f"  {ticker}: broker daily flow unavailable ({str(e)[:60]})")
            return None

    def _summary_fetch_ranges(
        self,
        ticker: str,
        requested_start: date,
        end_date: date,
        last_trading: date,
        request: RefreshBrokerDataRequest,
        notes: list[str],
    ) -> tuple[list[tuple[date, date, str]], date | None]:
        if request.refresh:
            return [(requested_start, end_date, "refresh")], None

        summary_range = self._repository.get_date_range(ticker, source="idx")
        if not summary_range:
            return [(requested_start, end_date, "initial")], None

        ranges: list[tuple[date, date, str]] = []
        summary_earliest, summary_latest = summary_range
        tolerated_start = requested_start + timedelta(
            days=request.requested_start_tolerance_days
        )
        needs_backfill = summary_earliest > tolerated_start
        needs_forward = summary_latest < last_trading
        if needs_backfill:
            cached_days = (summary_latest - summary_earliest).days
            notes.append(
                f"  broker  {ticker}: {cached_days}d idx summaries cached "
                f"(from {summary_earliest}), requested {request.days}d — backfilling older gap"
            )
            ranges.append((requested_start, summary_earliest - timedelta(days=1), "backfill"))
        if needs_forward:
            ranges.append((summary_latest + timedelta(days=1), end_date, "forward"))
        return ranges, summary_latest

    def _previous_flow_latest(self, ticker: str, source: str) -> date | None:
        flow_range = self._repository.get_foreign_flow_date_range(ticker, source=source)
        return flow_range[1] if flow_range else None

    def _refresh_foreign_flow_history(
        self,
        ticker: str,
        days: int,
        notes: list[str],
    ) -> None:
        try:
            points = self._broker_provider.fetch_foreign_flow_history(ticker, days=days)
            if points:
                self._repository.save_foreign_flow_points(points)
        except Exception as e:
            notes.append(f"  {ticker}: foreign-flow history unavailable ({str(e)[:60]})")

    def _summary_status(
        self,
        added_count: int,
        updated_range: tuple[date, date] | None,
        fetch_modes: set[str],
        fetch_ranges: list[tuple[date, date, str]],
        previous_latest: date | None,
    ) -> str:
        if added_count == 0 and not fetch_ranges and updated_range is not None:
            return f"✓({updated_range[1]})"
        if added_count == 0 and previous_latest is not None:
            return _no_new_data_status(previous_latest)
        if added_count == 0 and updated_range is not None:
            return f"✓({updated_range[1]})"
        return _range_update_status(added_count, updated_range, fetch_modes)

    def _flow_status(
        self,
        *,
        daily_resp: FetchBrokerDailyFlowsResponse | None,
        added_flow_count: int,
        updated_flow_range: tuple[date, date] | None,
        fetch_modes: set[str],
        latest_date: date | None,
        previous_flow_latest: date | None,
        last_trading: date,
        refresh: bool,
    ) -> str:
        if added_flow_count == 0 and previous_flow_latest is not None and daily_resp is None:
            if not refresh and previous_flow_latest < last_trading:
                return f"agg={_no_new_data_status(previous_flow_latest)}"
            return f"agg=✓({previous_flow_latest})"

        daily_part: str | None = None
        if daily_resp is not None:
            latest_daily = daily_resp.cached_range[1] if daily_resp.cached_range else None
            if daily_resp.fetched_count > 0:
                span = (
                    (daily_resp.cached_range[1] - daily_resp.cached_range[0]).days + 1
                    if daily_resp.cached_range
                    else 0
                )
                daily_part = (
                    f"daily:+{daily_resp.fetched_count}rows/"
                    f"{daily_resp.active_codes}codes/{span}d"
                )
            elif daily_resp.status == "cached" and latest_daily is not None:
                daily_part = f"daily=✓({latest_daily})"
            elif latest_daily is not None:
                daily_part = f"daily=up-to-date({latest_daily})"
            else:
                daily_part = f"daily={daily_resp.status}"

        flow_part: str | None = None
        if added_flow_count > 0 and updated_flow_range:
            span = (updated_flow_range[1] - updated_flow_range[0]).days + 1
            prefix = "backfill+" if "backfill" in fetch_modes else "+"
            flow_part = f"agg:{prefix}{added_flow_count}rows/{span}d"
        elif latest_date is not None:
            if not refresh and latest_date < last_trading:
                flow_part = f"agg=up-to-date({latest_date})"
            else:
                flow_part = f"agg=✓({latest_date})"

        if daily_part and flow_part:
            return f"{daily_part} {flow_part}"
        if daily_part:
            return daily_part
        if flow_part:
            return flow_part
        return f"✓({latest_date})" if latest_date else "✓"


def _no_new_data_status(latest: date | None) -> str:
    if latest is None:
        return "no-data"
    return f"up-to-date({latest.isoformat()})"


def _range_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (
        (updated_range[1] - updated_range[0]).days + 1
        if updated_range
        else 0
    )
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"
