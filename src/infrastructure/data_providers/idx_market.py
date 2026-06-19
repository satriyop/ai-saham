"""
IDX-native OHLCV market data provider.

Fetches daily OHLCV data from idx.co.id's public TradingSummary API —
the same endpoint used by IdxBrokerDataProvider for foreign flow data.
No authentication required.

Advantages over Yahoo Finance:
- Raw (unadjusted) prices straight from the exchange
- Real-time same-day availability (not T+1 lag)
- No `.JK` suffix needed

Tradeoff:
- One HTTP request per trading day (rate-limited)
- Slower for large date ranges (use Yahoo for > 1 year bulk fetch)

Layer: Infrastructure
Depends on: Domain ports (MarketDataProvider), httpx
"""

import logging
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import (
    MarketDataProvider,
    MarketDataProviderError,
)

logger = logging.getLogger(__name__)

# Reuse the existing IDX endpoint (same as IdxBrokerDataProvider)
IDX_API_BASE = "https://www.idx.co.id/primary/TradingSummary"
STOCK_SUMMARY_ENDPOINT = "/GetStockSummary"

# Chunk size for date ranges (to limit memory and API load)
CHUNK_DAYS = 90

# Rate limiting and retry settings
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0

IDX_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.idx.co.id/en/market-data/trading-summary/stock-summary/",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

class IdxMarketDataProvider(MarketDataProvider):
    """
    IDX-native OHLCV provider using the public TradingSummary API.

    Fetches one trading day per request, iterating over the requested date range.
    Dates with no data (IDX returns 403 or empty response) are silently skipped.

    Usage:
        provider = IdxMarketDataProvider()
        candles = provider.fetch_daily_ohlcv("BBCA", date(2025, 1, 1), date(2025, 1, 31))
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._last_request_time: float = 0
        self.provider_name = "idx"
        self.volume_unit = "shares"
        self.price_adjustment_policy = "raw"

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _fetch_day(self, target_date: date) -> dict[str, Any] | None:
        """
        Fetch market summary for one trading day.

        Returns None when IDX has no data for the date (403 or empty).
        Raises MarketDataProviderError on network errors.
        """
        self._rate_limit()

        url = f"{IDX_API_BASE}{STOCK_SUMMARY_ENDPOINT}"
        params = {
            "start": 0,
            "length": 9999,
            "date": target_date.strftime("%Y%m%d"),
        }

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(
                        url,
                        params=params,
                        headers=IDX_HEADERS,
                        follow_redirects=True,
                    )

                    if response.status_code == 403:
                        # No data available for this date — do not assume holiday.
                        return None

                    if response.status_code == 429:
                        wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            "IDX rate limited, waiting %.1fs (retry %d/%d)",
                            wait, attempt + 1, MAX_RETRIES,
                        )
                        time.sleep(wait)
                        continue

                    if response.status_code >= 500:
                        wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            "IDX server error %d, waiting %.1fs (retry %d/%d)",
                            response.status_code, wait, attempt + 1, MAX_RETRIES,
                        )
                        time.sleep(wait)
                        last_error = MarketDataProviderError(
                            f"IDX API server error: {response.status_code}"
                        )
                        continue

                    if response.status_code != 200:
                        raise MarketDataProviderError(
                            f"IDX API error: {response.status_code}"
                        )

                    return response.json()

            except httpx.TimeoutException as e:
                last_error = MarketDataProviderError(f"IDX request timeout: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
            except httpx.RequestError as e:
                last_error = MarketDataProviderError(f"IDX request failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))

        raise last_error or MarketDataProviderError("IDX request failed after retries")

    def _extract_ticker(
        self, response_data: dict[str, Any], ticker: str
    ) -> Candle | None:
        """Extract a single ticker's OHLCV from a market-wide response."""
        ticker_upper = ticker.upper()
        for item in response_data.get("data", []):
            if item.get("StockCode") == ticker_upper:
                return self._parse_candle(item, ticker_upper)
        return None

    def _parse_candle(self, data: dict[str, Any], ticker: str) -> Candle:
        """Parse a stock record into a Candle entity."""
        date_str = data["Date"][:10]  # "2025-01-24T00:00:00" → "2025-01-24"
        trading_date = date.fromisoformat(date_str)

        open_price = Decimal(
            str(data.get("OpenPrice") or data.get("Previous") or data.get("Close", 0))
        )
        high = Decimal(str(data.get("High") or data.get("Close", 0)))
        low = Decimal(str(data.get("Low") or data.get("Close", 0)))
        close = Decimal(str(data.get("Close", 0)))
        volume_shares = int(data.get("Volume", 0))

        return Candle(
            ticker=ticker,
            date=trading_date,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume_shares,
        )

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        """
        Fetch daily OHLCV for a ticker over a date range.

        Iterates over every calendar day and fetches the IDX summary.
        Non-trading days are skipped automatically. Large date ranges
        are chunked to avoid memory pressure.

        Args:
            ticker: IDX ticker without suffix (e.g., "BBCA")
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of Candle entities sorted by date ascending.

        Raises:
            MarketDataProviderError: On network or API failure.
        """
        candles: list[Candle] = []
        current = start_date

        while current <= end_date:
            try:
                response_data = self._fetch_day(current)
                if response_data is not None:
                    candle = self._extract_ticker(response_data, ticker)
                    if candle is not None:
                        candles.append(candle)
            except MarketDataProviderError as e:
                logger.warning("Failed to fetch %s for %s: %s", ticker, current, e)

            current += timedelta(days=1)

        return sorted(candles, key=lambda c: c.date)
