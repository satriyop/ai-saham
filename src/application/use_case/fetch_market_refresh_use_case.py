"""
Application orchestration for `saham fetch market`.

Layer: Application
AI usage: None
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.application.ports.universe_config_loader import UniverseConfigLoader
from src.application.services.fetch_market_status_policy import is_cached_status
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.fetch_enrichment_history_use_case import (
    EnrichmentPitTableCoverage,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.value_objects.benchmark_symbol import (
    CANONICAL_BENCHMARK_TICKER,
    canonicalize_ticker,
    is_benchmark_ticker,
)

BENCHMARK_TICKER = CANONICAL_BENCHMARK_TICKER


@dataclass(frozen=True)
class BrokerFetchResult:
    """Split status for broker summary and flow refreshes."""

    summaries: str
    flow: str


@dataclass(frozen=True)
class FetchMarketTickerResult:
    ticker: str
    candles_status: str
    broker_result: BrokerFetchResult
    meta_status: str
    enrichment_status: str
    any_error: bool
    all_cached: bool


@dataclass(frozen=True)
class FetchMarketRefreshRequest:
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


@dataclass(frozen=True)
class FetchMarketRefreshResponse:
    ticker_list: list[str]
    stock_tickers_only: list[str]
    ticker_results: list[FetchMarketTickerResult]
    ok_count: int
    fail_count: int
    failures: list[str] = field(default_factory=list)
    candle_short_history: list[str] = field(default_factory=list)
    broker_backfills: list[str] = field(default_factory=list)
    meta_changed: list[str] = field(default_factory=list)
    enrichment_available: bool = False
    pit_coverage: list[EnrichmentPitTableCoverage] = field(default_factory=list)


class FetchMarketRefreshUseCase:
    """Coordinate a market refresh without owning provider construction or output."""

    def __init__(
        self,
        fetch_candles: Callable[..., str],
        fetch_broker: Callable[..., BrokerFetchResult],
        fetch_meta: Callable[..., str],
        fetch_enrichment: Callable[..., str],
        universe_loader: UniverseConfigLoader,
        broker_repository: BrokerDataRepository | None = None,
        read_pit_coverage: Callable[[], list[EnrichmentPitTableCoverage]] | None = None,
    ) -> None:
        self._fetch_candles = fetch_candles
        self._fetch_broker = fetch_broker
        self._fetch_meta = fetch_meta
        self._fetch_enrichment = fetch_enrichment
        self._universe_loader = universe_loader
        self._broker_repo = broker_repository
        self._read_pit_coverage = read_pit_coverage

    def execute(
        self,
        request: FetchMarketRefreshRequest,
        on_ticker_complete: Callable[[FetchMarketTickerResult, int, int], None] | None = None,
    ) -> FetchMarketRefreshResponse:
        ticker_list = resolve_tickers(
            universe=request.universe,
            explicit=request.tickers,
            db_path=request.db_path,
            loader=self._universe_loader,
            repository=self._broker_repo,
        )
        if not ticker_list:
            return FetchMarketRefreshResponse(
                ticker_list=[],
                stock_tickers_only=[],
                ticker_results=[],
                ok_count=0,
                fail_count=0,
            )

        ticker_list = self._with_benchmark_first(ticker_list)
        enrichment_available = (
            not request.no_enrichment
            and request.broker_provider_name == "stockbit"
        )

        ok_count = 0
        fail_count = 0
        failures: list[str] = []
        ticker_results: list[FetchMarketTickerResult] = []
        candle_short_history: list[str] = []
        broker_backfills: list[str] = []
        meta_changed: list[str] = []

        for ticker in ticker_list:
            candles_status = "skip"
            broker_result = BrokerFetchResult(summaries="skip", flow="skip")
            meta_status = "skip"
            enrichment_status = "skip"

            if not request.broker_only:
                candles_status = self._fetch_candles(
                    ticker=ticker,
                    days=request.days,
                    db_path=request.db_path,
                    provider_name=request.candles_provider,
                    refresh=request.refresh,
                    short_history=candle_short_history,
                )

            if not request.candles_only:
                broker_result = self._fetch_broker(
                    ticker=ticker,
                    days=request.days,
                    db_path=request.db_path,
                    broker_provider=request.broker_provider,
                    refresh=request.refresh,
                    short_history=broker_backfills,
                )

            if not request.no_meta:
                meta_status = self._fetch_meta(ticker, request.db_path)
                if meta_status.startswith("changed"):
                    meta_changed.append(f"  {ticker}: {meta_status}")

            if enrichment_available:
                enrichment_status = self._fetch_enrichment(
                    ticker,
                    request.db_path,
                    request.broker_provider,
                    force_refresh=request.refresh,
                )

            any_error = (
                "ERR:" in candles_status
                or "ERR:" in broker_result.summaries
                or "ERR:" in broker_result.flow
                or "ERR:" in enrichment_status
            )
            all_cached = (
                is_cached_status(candles_status)
                and is_cached_status(broker_result.summaries)
                and is_cached_status(broker_result.flow)
                and (request.no_meta or meta_status.startswith("cached"))
                and (not enrichment_available or enrichment_status.startswith("✓"))
            )

            if any_error:
                fail_count += 1
                failures.append(ticker)
            else:
                ok_count += 1

            result_item = FetchMarketTickerResult(
                ticker=ticker,
                candles_status=candles_status,
                broker_result=broker_result,
                meta_status=meta_status,
                enrichment_status=enrichment_status,
                any_error=any_error,
                all_cached=all_cached,
            )
            ticker_results.append(result_item)

            if on_ticker_complete is not None:
                on_ticker_complete(result_item, len(ticker_results), len(ticker_list))

        stock_tickers_only = [
            ticker for ticker in ticker_list
            if not is_benchmark_ticker(ticker) and not ticker.startswith("^")
        ]
        pit_coverage: list[EnrichmentPitTableCoverage] = []
        if enrichment_available and self._read_pit_coverage is not None:
            pit_coverage = self._read_pit_coverage()
        return FetchMarketRefreshResponse(
            ticker_list=ticker_list,
            stock_tickers_only=stock_tickers_only,
            ticker_results=ticker_results,
            ok_count=ok_count,
            fail_count=fail_count,
            failures=failures,
            candle_short_history=candle_short_history,
            broker_backfills=broker_backfills,
            meta_changed=meta_changed,
            enrichment_available=enrichment_available,
            pit_coverage=pit_coverage,
        )

    def _with_benchmark_first(self, tickers: list[str]) -> list[str]:
        seen: set[str] = set()
        without_benchmark: list[str] = []
        for ticker in tickers:
            canonical = canonicalize_ticker(ticker)
            if canonical == BENCHMARK_TICKER or canonical in seen:
                continue
            seen.add(canonical)
            without_benchmark.append(canonical)
        return [BENCHMARK_TICKER] + without_benchmark
