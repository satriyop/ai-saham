"""
FetchStockMetaUseCase — fetch and cache sector/industry metadata for a ticker.

Orchestrates:
  1. TTL check  — skip network call if cached data is fresh enough
  2. Fetch      — call provider (Yahoo Finance) for current classification
  3. Change det — compare checksum; only write if classification changed or new
  4. Persist    — save updated record to repository

Layer: Application
"""

from dataclasses import dataclass
from typing import Literal

from src.domain.ports.stock_meta_provider import StockMetaProvider
from src.domain.ports.stock_meta_repository import StockMetaRepository

# TODO: move to settings file or env var (e.g. SAHAM_META_TTL_DAYS)
META_TTL_DAYS = 30

MetaStatus = Literal["cached", "new", "verified", "changed", "error"]


@dataclass(frozen=True)
class FetchStockMetaRequest:
    ticker: str
    ttl_days: int = META_TTL_DAYS


@dataclass(frozen=True)
class FetchStockMetaResult:
    ticker: str
    status: MetaStatus      # 'cached' | 'new' | 'verified' | 'changed' | 'error'
    sector: str | None
    industry: str | None
    cached_days: int | None  # how old the cached record is (None if new/error)
    error: str | None = None


class FetchStockMetaUseCase:
    def __init__(
        self,
        provider: StockMetaProvider,
        repository: StockMetaRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(self, request: FetchStockMetaRequest) -> FetchStockMetaResult:
        ticker = request.ticker.upper()

        # 1. TTL check — return cached if fresh enough
        if not self._repository.needs_refresh(ticker, request.ttl_days):
            existing = self._repository.get(ticker)
            age_days = self._repository.cached_age_days(ticker)
            return FetchStockMetaResult(
                ticker=ticker,
                status="cached",
                sector=existing.sector if existing else None,
                industry=existing.industry if existing else None,
                cached_days=age_days,
            )

        # 2. Fetch from external provider
        try:
            fresh = self._provider.fetch(ticker)
        except Exception as e:
            return FetchStockMetaResult(
                ticker=ticker,
                status="error",
                sector=None,
                industry=None,
                cached_days=None,
                error=str(e)[:80],
            )

        if fresh is None:
            return FetchStockMetaResult(
                ticker=ticker,
                status="error",
                sector=None,
                industry=None,
                cached_days=None,
                error="provider returned no data",
            )

        # 3. Compare checksum against stored record
        existing = self._repository.get(ticker)
        is_new = existing is None
        changed = not is_new and existing.checksum != fresh.checksum

        # 4. Persist (always write — updates fetched_at even when sector unchanged)
        self._repository.save(fresh)

        status: MetaStatus = "new" if is_new else ("changed" if changed else "verified")
        return FetchStockMetaResult(
            ticker=ticker,
            status=status,
            sector=fresh.sector,
            industry=fresh.industry,
            cached_days=None,
        )
