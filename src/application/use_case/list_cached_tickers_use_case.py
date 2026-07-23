"""List locally-cached tickers for offline ticker-search autocomplete.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.cached_ticker_catalog import CachedTickerCatalog


@dataclass(frozen=True)
class ListCachedTickersRequest:
    prefix: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class ListCachedTickersResult:
    tickers: tuple[str, ...]
    total_cached: int


class ListCachedTickersUseCase:
    """Return cached tickers, optionally narrowed by a case-insensitive prefix.

    This is a read-only, offline query — it never contacts a provider. It backs
    the Ticker Decision Workbench global search so any ticker with local data can
    be opened, whether or not it belongs to a configured universe.
    """

    def __init__(self, catalog: CachedTickerCatalog) -> None:
        self._catalog = catalog

    def execute(
        self, request: ListCachedTickersRequest | None = None
    ) -> ListCachedTickersResult:
        req = request or ListCachedTickersRequest()
        all_tickers = [t.upper() for t in self._catalog.list_tickers()]

        matches = all_tickers
        if req.prefix:
            needle = req.prefix.strip().upper()
            matches = [t for t in all_tickers if t.startswith(needle)]

        if req.limit is not None and req.limit >= 0:
            matches = matches[: req.limit]

        return ListCachedTickersResult(
            tickers=tuple(matches),
            total_cached=len(all_tickers),
        )
