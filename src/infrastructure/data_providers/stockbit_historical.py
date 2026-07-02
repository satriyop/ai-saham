"""
StockbitHistoricalProvider — daily OHLCV from Stockbit /company-price-feed/historical/summary.

Implements MarketDataProvider as a fallback/alternative to Yahoo Finance.
Useful for tickers not available on Yahoo (.JK suffix issues, small caps, etc.)

Confirmed response shape (live probe 2026-06-20):
  data.result[].date   → "YYYY-MM-DD"
  data.result[].open   → int (IDR per share)
  data.result[].high   → int
  data.result[].low    → int
  data.result[].close  → int/float
  data.result[].volume → int LOTS (1 lot = 100 shares)
  data.result[].value  → int IDR total traded value
  Pagination: ?period=HS_PERIOD_DAILY&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=50&page=N

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from src.domain.value_objects.benchmark_symbol import canonicalize_ticker
from src.domain.value_objects import is_non_idx_ticker
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import MarketDataProvider
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

_LOTS_PER_SHARE = 100
_PAGE_LIMIT = 50


# IDX stock prices are integer IDR; IHSG index level is conventionally 3dp.
# When Stockbit returns a Python float (e.g. for in-progress intraday sessions)
# we round to this precision before converting to Decimal to avoid IEEE 754
# binary noise (e.g. 5737.73583984375 instead of 5737.736).
_PRICE_DECIMAL_PLACES = 3


def _parse_decimal(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, float):
            return Decimal(str(round(raw, _PRICE_DECIMAL_PLACES)))
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_ohlcv_rows(ticker: str, rows: list[dict]) -> list[Candle]:
    """Convert raw API rows to Candle entities. Skips malformed rows silently."""
    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            d = date.fromisoformat(str(row.get("date") or "")[:10])
        except (ValueError, TypeError):
            continue

        open_ = _parse_decimal(row.get("open"))
        high = _parse_decimal(row.get("high"))
        low = _parse_decimal(row.get("low"))
        close = _parse_decimal(row.get("close"))
        vol_lots = row.get("volume")

        if None in (open_, high, low, close) or vol_lots is None:
            continue

        try:
            volume_shares = int(vol_lots) * _LOTS_PER_SHARE
            candles.append(Candle(
                ticker=ticker.upper(),
                date=d,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume_shares,
            ))
        except (ValueError, TypeError, Exception) as exc:
            logger.debug("skipping bad row for %s on %s: %s", ticker, row.get("date"), exc)

    return sorted(candles, key=lambda c: c.date)


class StockbitHistoricalProvider(MarketDataProvider):
    """Daily OHLCV provider using Stockbit Exodus historical/summary endpoint.

    Requires an authenticated StockbitPlaywrightBrokerProvider to obtain the
    Bearer token. Pagination is handled internally (50 rows per page).

    Args:
        broker_provider: Authenticated Stockbit session for token access.
    """

    provider_name = "stockbit"
    volume_unit = "shares"          # lots converted to shares (* 100) on ingest
    price_adjustment_policy = "raw"

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        non_idx_tickers: set[str] | None = None,
    ) -> None:
        self._api_client = api_client
        self._non_idx_tickers = non_idx_tickers or set()

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        """Fetch OHLCV candles from Stockbit, walking paginated responses.

        Returns empty list (not an exception) when the provider is unavailable
        or returns no data, so the caller can fall back to another source.
        """
        if self._api_client is None:
            return []

        canonical_ticker = canonicalize_ticker(ticker)
        if is_non_idx_ticker(canonical_ticker, self._non_idx_tickers):
            return []

        base_url = STOCKBIT_CFG.historical_summary_url.format(ticker=canonical_ticker)
        all_candles: list[Candle] = []
        page = 1

        try:
            while True:
                url = (
                    f"{base_url}"
                    f"?period=HS_PERIOD_DAILY"
                    f"&start_date={start_date.isoformat()}"
                    f"&end_date={end_date.isoformat()}"
                    f"&limit={_PAGE_LIMIT}&page={page}"
                )
                body = self._api_client.get(url)
                if not body:
                    break
                rows = (body.get("data") or {}).get("result") or []
                if not rows:
                    break
                all_candles.extend(_parse_ohlcv_rows(canonical_ticker, rows))
                if len(rows) < _PAGE_LIMIT:
                    break
                page += 1
        except Exception as exc:
            logger.debug("StockbitHistoricalProvider: fetch failed for %s: %s", ticker, exc)
            if all_candles:
                return sorted(all_candles, key=lambda c: c.date)
            return []

        return sorted(all_candles, key=lambda c: c.date)
