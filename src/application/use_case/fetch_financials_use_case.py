"""
FetchFinancialsUseCase — fetch and cache multi-period financial statements.

Owns freshness policy (TTL + force refresh), per-ticker orchestration, and
status aggregation. Provider and repository are injected ports.

Default source path is yfinance (source label ``yahoo``). Stockbit gap-fill
is intentionally out of scope for Phase A.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.domain.ports.financials_provider import FinancialsProvider
from src.domain.ports.financials_repository import FinancialsRepository

DEFAULT_FINANCIALS_TTL_DAYS = 7
DEFAULT_FINANCIALS_SOURCE = "yahoo"

FinancialsStatus = Literal["cached", "fetched", "empty", "error"]


@dataclass(frozen=True)
class FetchFinancialsRequest:
    tickers: tuple[str, ...]
    force_refresh: bool = False
    ttl_days: int = DEFAULT_FINANCIALS_TTL_DAYS
    include_quarterly: bool = True
    include_annual: bool = True
    source: str = DEFAULT_FINANCIALS_SOURCE


@dataclass(frozen=True)
class FetchFinancialsTickerResult:
    ticker: str
    status: FinancialsStatus
    periods_stored: int
    latest_period_end: date | None
    error: str | None = None


@dataclass(frozen=True)
class FetchFinancialsResponse:
    results: tuple[FetchFinancialsTickerResult, ...]

    @property
    def fetched_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fetched")

    @property
    def cached_count(self) -> int:
        return sum(1 for r in self.results if r.status == "cached")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.status == "error")


class FetchFinancialsUseCase:
    """Cache-aware multi-ticker financial statement refresh."""

    def __init__(
        self,
        provider: FinancialsProvider,
        repository: FinancialsRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(self, request: FetchFinancialsRequest) -> FetchFinancialsResponse:
        results: list[FetchFinancialsTickerResult] = []
        for raw in request.tickers:
            ticker = raw.upper().strip()
            if not ticker:
                continue
            results.append(self._process_ticker(ticker, request))
        return FetchFinancialsResponse(results=tuple(results))

    def _process_ticker(
        self,
        ticker: str,
        request: FetchFinancialsRequest,
    ) -> FetchFinancialsTickerResult:
        source = request.source

        if not request.force_refresh and not self._repository.needs_refresh(
            ticker, request.ttl_days, source=source
        ):
            latest = self._repository.latest_period_end(ticker, source=source)
            stored = len(self._repository.list_for_ticker(ticker, source=source))
            return FetchFinancialsTickerResult(
                ticker=ticker,
                status="cached",
                periods_stored=stored,
                latest_period_end=latest,
            )

        try:
            periods = self._provider.fetch_statements(
                ticker,
                include_quarterly=request.include_quarterly,
                include_annual=request.include_annual,
            )
        except Exception as exc:
            return FetchFinancialsTickerResult(
                ticker=ticker,
                status="error",
                periods_stored=0,
                latest_period_end=self._repository.latest_period_end(ticker, source=source),
                error=str(exc)[:120],
            )

        if not periods:
            return FetchFinancialsTickerResult(
                ticker=ticker,
                status="empty",
                periods_stored=0,
                latest_period_end=self._repository.latest_period_end(ticker, source=source),
                error="provider returned no periods",
            )

        written = self._repository.upsert_many(periods)
        latest = max((p.period_end for p in periods), default=None)
        return FetchFinancialsTickerResult(
            ticker=ticker,
            status="fetched",
            periods_stored=written,
            latest_period_end=latest,
        )
