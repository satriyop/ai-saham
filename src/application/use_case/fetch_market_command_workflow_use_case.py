"""
Workflow orchestration use case for fetch market CLI command.

Layer: Application
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.application.services.fetch_market_provider_precondition import (
    FetchMarketProviderPrecondition,
    FetchMarketProviderPreconditionRequest,
)
from src.application.services.market_freshness_service import (
    BenchmarkTickerAliases,
    MarketFreshnessService,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BENCHMARK_TICKER,
    FetchMarketRefreshRequest,
    FetchMarketRefreshResponse,
    FetchMarketRefreshUseCase,
    FetchMarketTickerResult,
)
from src.application.use_case.refresh_market_context_inputs_use_case import (
    RefreshMarketContextInputsResponse,
)
from src.domain.value_objects.benchmark_symbol import YAHOO_IHSG_TICKER, canonicalize_ticker


@dataclass(frozen=True)
class FetchMarketCommandWorkflowRequest:
    tickers: list[str]
    universe: str | None
    days: int
    db_path: Path
    candles_provider: str
    broker_provider: Any
    broker_provider_name: str
    refresh: bool
    candles_only: bool
    broker_only: bool
    no_meta: bool
    no_enrichment: bool
    no_calendar: bool


@dataclass(frozen=True)
class FetchMarketStatusHeader:
    line: str
    is_open: bool


@dataclass(frozen=True)
class FetchMarketCommandStartEvent:
    market_status_line: str | None
    market_is_open: bool
    ticker_count: int
    days: int
    candles_provider: str
    broker_provider_name: str
    no_meta: bool
    candles_only: bool
    broker_only: bool
    enrichment_available: bool


@dataclass(frozen=True)
class FetchMarketCommandWorkflowResult:
    response: FetchMarketRefreshResponse
    header: FetchMarketStatusHeader | None
    calendar_status: str
    expected_trading_day: date
    context_statuses: tuple[str, ...]


class FetchMarketCommandWorkflowUseCase:
    """Coordinate a market refresh workflow run, validating pre-conditions first

    and fetching status headers, candles, broker records, calendars, and context inputs.
    """

    def __init__(
        self,
        refresh_use_case: FetchMarketRefreshUseCase,
        provider_precondition: FetchMarketProviderPrecondition,
        non_idx_tickers_loader: Callable[[], frozenset[str]],
        market_status_loader: Callable[[], FetchMarketStatusHeader | None],
        calendar_refresh: Callable[[Path, Any, bool], str],
        context_refresh: Callable[[Path, int], RefreshMarketContextInputsResponse],
        market_freshness: MarketFreshnessService,
        ticker_resolver: Callable[[str | None, list[str], Path], list[str]],
    ) -> None:
        self._refresh_use_case = refresh_use_case
        self._provider_precondition = provider_precondition
        self._non_idx_tickers_loader = non_idx_tickers_loader
        self._market_status_loader = market_status_loader
        self._calendar_refresh = calendar_refresh
        self._context_refresh = context_refresh
        self._market_freshness = market_freshness
        self._ticker_resolver = ticker_resolver

    def execute(
        self,
        request: FetchMarketCommandWorkflowRequest,
        on_ticker_complete: Callable[[FetchMarketTickerResult, int, int], None] | None = None,
        on_start: Callable[[FetchMarketCommandStartEvent], None] | None = None,
    ) -> FetchMarketCommandWorkflowResult:
        # 1. Resolve tickers
        ticker_list = self._ticker_resolver(
            request.universe,
            request.tickers,
            request.db_path,
        )

        if not ticker_list:
            raise ValueError(
                "No tickers to update. Specify --universe or provide ticker arguments."
            )

        # Preserve benchmark-first normalization before provider precondition validation
        without_benchmark = [
            canonicalize_ticker(t) for t in ticker_list
            if canonicalize_ticker(t) != BENCHMARK_TICKER
        ]
        full_ticker_list = [BENCHMARK_TICKER] + list(dict.fromkeys(without_benchmark))

        # 2. Provider precondition validation
        if not request.broker_only:
            precondition_error = self._provider_precondition.validate(
                FetchMarketProviderPreconditionRequest(
                    tickers=full_ticker_list,
                    non_idx_tickers=self._non_idx_tickers_loader(),
                    candles_provider=request.candles_provider,
                    has_broker_session=request.broker_provider_name == "stockbit",
                )
            )
            if precondition_error is not None:
                raise ValueError(precondition_error)

        # 3. Load market status
        header = self._market_status_loader()

        # 4. Call on_start
        enrichment_available = (
            not request.no_enrichment
            and request.broker_provider_name == "stockbit"
        )
        if on_start is not None:
            on_start(
                FetchMarketCommandStartEvent(
                    market_status_line=header.line if header else None,
                    market_is_open=header.is_open if header else False,
                    ticker_count=len(full_ticker_list),
                    days=request.days,
                    candles_provider=request.candles_provider,
                    broker_provider_name=request.broker_provider_name,
                    no_meta=request.no_meta,
                    candles_only=request.candles_only,
                    broker_only=request.broker_only,
                    enrichment_available=enrichment_available,
                )
            )

        # 5. Execute per-ticker refresh
        refresh_req = FetchMarketRefreshRequest(
            tickers=full_ticker_list,
            universe=None,  # pass None to avoid resolving the same universe twice
            days=request.days,
            db_path=request.db_path,
            candles_provider=request.candles_provider,
            broker_provider=request.broker_provider,
            broker_provider_name=request.broker_provider_name,
            refresh=request.refresh,
            candles_only=request.candles_only,
            broker_only=request.broker_only,
            no_meta=request.no_meta,
            no_enrichment=request.no_enrichment,
        )
        response = self._refresh_use_case.execute(
            refresh_req,
            on_ticker_complete=on_ticker_complete,
        )

        # 6. Run calendar refresh
        if request.no_calendar:
            calendar_status = "skip:--no-calendar"
        elif request.no_enrichment:
            calendar_status = "skip:--no-enrichment"
        elif request.broker_provider_name != "stockbit":
            calendar_status = "skip:no-stockbit"
        else:
            calendar_status = self._calendar_refresh(
                request.db_path,
                request.broker_provider.api_client,
                request.refresh,
            )

        # 7. Run context refresh
        context_statuses: tuple[str, ...] = ()
        if not request.broker_only:
            context_response = self._context_refresh(request.db_path, request.days)
            context_statuses = context_response.statuses

        # 8. Expected trading day computation
        aliases = BenchmarkTickerAliases(canonical=BENCHMARK_TICKER, legacy=YAHOO_IHSG_TICKER)
        expected_trading_day = self._market_freshness.resolve_reference_trading_day(
            aliases, date.today()
        )

        # 9. Return final result
        return FetchMarketCommandWorkflowResult(
            response=response,
            header=header,
            calendar_status=calendar_status,
            expected_trading_day=expected_trading_day,
            context_statuses=context_statuses,
        )
