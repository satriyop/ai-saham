"""
Sector/industry metadata refresh helpers for `saham fetch market`.

Owns per-ticker sector/industry metadata refresh via Yahoo Finance,
cached with a TTL by FetchStockMetaUseCase.

Layer: Infrastructure composition
"""

from pathlib import Path

from src.application.use_case.fetch_stock_meta_use_case import (
    FetchStockMetaRequest,
    FetchStockMetaUseCase,
)
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker, is_benchmark_ticker
from src.infrastructure.data_providers.yahoo_stock_meta import YahooStockMetaProvider
from src.infrastructure.persistence.sqlite_stock_meta_repository import (
    SQLiteStockMetaRepository,
)


def fetch_meta(ticker: str, db_path: Path) -> str:
    """Fetch sector/industry metadata for one ticker. Returns a status string."""
    ticker = canonicalize_ticker(ticker)
    if is_benchmark_ticker(ticker) or ticker.startswith("^"):
        return "n/a:index"

    try:
        repo = SQLiteStockMetaRepository(db_path)
        provider = YahooStockMetaProvider()
        use_case = FetchStockMetaUseCase(provider=provider, repository=repo)
        result = use_case.execute(FetchStockMetaRequest(ticker=ticker))

        if result.status == "cached":
            return f"cached({result.cached_days}d)"
        if result.status == "new":
            return f"new({result.sector or '?'})"
        if result.status == "changed":
            return f"changed→{result.sector or '?'}"
        if result.status == "verified":
            return "verified"
        # error
        return f"ERR:{(result.error or 'unknown')[:30]}"
    except Exception as e:
        return f"ERR:{str(e)[:30]}"
