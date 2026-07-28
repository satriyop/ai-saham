"""
FetchFinancialsUseCase — fetch and cache multi-period financial statements.

Owns per-statement_kind freshness policy, force refresh, and status aggregation.
Default source path is yfinance (source label ``yahoo``).

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.domain.ports.financials_provider import FinancialsProvider
from src.domain.ports.financials_repository import FinancialsRepository
from src.domain.value_objects.company_financial_period import (
    ALL_STATEMENT_KINDS,
    FinancialStatementKind,
)

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
    statement_kinds: frozenset[FinancialStatementKind] = ALL_STATEMENT_KINDS
    source: str = DEFAULT_FINANCIALS_SOURCE


@dataclass(frozen=True)
class FetchFinancialsTickerResult:
    ticker: str
    status: FinancialsStatus
    periods_stored: int
    latest_period_end: date | None
    kinds_fetched: tuple[FinancialStatementKind, ...] = ()
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
    """Cache-aware multi-ticker, multi-kind financial statement refresh."""

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
        kinds = frozenset(request.statement_kinds) or ALL_STATEMENT_KINDS

        kinds_to_fetch: list[FinancialStatementKind] = []
        for kind in sorted(kinds):
            if request.force_refresh or self._repository.needs_refresh(
                ticker, request.ttl_days, source=source, statement_kind=kind
            ):
                kinds_to_fetch.append(kind)

        if not kinds_to_fetch:
            latest = self._latest_across(ticker, kinds, source)
            stored = sum(
                len(self._repository.list_for_ticker(ticker, statement_kind=k, source=source))
                for k in kinds
            )
            return FetchFinancialsTickerResult(
                ticker=ticker,
                status="cached",
                periods_stored=stored,
                latest_period_end=latest,
                kinds_fetched=(),
            )

        try:
            periods = self._provider.fetch_statements(
                ticker,
                include_quarterly=request.include_quarterly,
                include_annual=request.include_annual,
                statement_kinds=frozenset(kinds_to_fetch),
            )
        except Exception as exc:
            return FetchFinancialsTickerResult(
                ticker=ticker,
                status="error",
                periods_stored=0,
                latest_period_end=self._latest_across(ticker, kinds, source),
                kinds_fetched=(),
                error=str(exc)[:120],
            )

        if not periods:
            return FetchFinancialsTickerResult(
                ticker=ticker,
                status="empty",
                periods_stored=0,
                latest_period_end=self._latest_across(ticker, kinds, source),
                kinds_fetched=tuple(kinds_to_fetch),
                error="provider returned no periods",
            )

        written = self._repository.upsert_many(periods)
        latest = max((p.period_end for p in periods), default=None)
        fetched_kinds = tuple(sorted({p.statement_kind for p in periods}))
        return FetchFinancialsTickerResult(
            ticker=ticker,
            status="fetched",
            periods_stored=written,
            latest_period_end=latest,
            kinds_fetched=fetched_kinds,
        )

    def _latest_across(
        self,
        ticker: str,
        kinds: frozenset[FinancialStatementKind],
        source: str,
    ) -> date | None:
        ends: list[date] = []
        for kind in kinds:
            end = self._repository.latest_period_end(ticker, statement_kind=kind, source=source)
            if end is not None:
                ends.append(end)
        return max(ends) if ends else None
