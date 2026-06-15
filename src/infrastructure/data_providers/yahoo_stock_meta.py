"""
Yahoo Finance implementation of StockMetaProvider.

Fetches sector / industry classification via yfinance .info.
Uses Yahoo's GICS-based taxonomy (sector, industry).

Source field: 'yahoo'

Future: when IDX IDXIC endpoint becomes available, add an IdxStockMetaProvider
that implements the same port and set source='idxic'.

Layer: Infrastructure
"""

import hashlib
from datetime import datetime, timezone

import yfinance as yf

from src.domain.entities.stock_meta import StockMeta
from src.domain.ports.stock_meta_provider import StockMetaProvider

_SOURCE = "yahoo"
_MARKET_SUFFIX = ".JK"


def _checksum(sector: str | None, industry: str | None) -> str:
    raw = f"{sector or ''}|{industry or ''}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _to_yahoo_ticker(ticker: str) -> str:
    """BBCA → BBCA.JK  |  ^JKSE → ^JKSE (pass-through)."""
    if ticker.startswith("^") or "." in ticker:
        return ticker
    return ticker + _MARKET_SUFFIX


class YahooStockMetaProvider(StockMetaProvider):
    """
    Fetches sector/industry from Yahoo Finance .info endpoint.

    One HTTP call per ticker (~0.3–1s). Results are cached in SQLiteStockMetaRepository
    with a TTL so this is only called when data is stale.
    """

    def fetch(self, ticker: str) -> StockMeta | None:
        yahoo_sym = _to_yahoo_ticker(ticker.upper())
        info = yf.Ticker(yahoo_sym).info

        # yfinance returns {'trailingPegRatio': None, ...} for invalid tickers
        if not info or info.get("quoteType") is None:
            return None

        sector = info.get("sector") or None
        sector_key = info.get("sectorKey") or None
        industry = info.get("industry") or None
        industry_key = info.get("industryKey") or None
        name = info.get("longName") or info.get("shortName") or None

        return StockMeta(
            ticker=ticker.upper(),
            name=name,
            sector=sector,
            sector_key=sector_key,
            industry=industry,
            industry_key=industry_key,
            source=_SOURCE,
            fetched_at=datetime.now(tz=timezone.utc),
            checksum=_checksum(sector, industry),
        )
