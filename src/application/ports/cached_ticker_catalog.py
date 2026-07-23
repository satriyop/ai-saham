"""Port: read-only catalog of tickers that already have locally cached data.

Used by the Ticker Decision Workbench global search to offer offline
autocomplete without ever touching a provider.

Layer: Application (port)
"""

from __future__ import annotations

from typing import Protocol


class CachedTickerCatalog(Protocol):
    """Lists tickers that have cached market data available locally."""

    def list_tickers(self) -> list[str]:
        """Return the distinct cached tickers, upper-cased and sorted ascending."""
        ...
