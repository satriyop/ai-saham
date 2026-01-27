"""
IDX (Indonesia Stock Exchange) broker data provider.

Fetches stock summary data from idx.co.id's public API.
No authentication required - uses the publicly available
TradingSummary/GetStockSummary endpoint.

Layer: Infrastructure
Depends on: Domain ports, httpx

Data source: https://www.idx.co.id/en/market-data/trading-summary/stock-summary/

Limitations vs Stockbit provider:
- No per-broker breakdown (top_buyers/top_sellers will be empty)
- Foreign flow values are estimated (volume * closing price)
- Foreign flow lots are exact (from ForeignBuy/ForeignSell fields)
"""

import logging
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from src.domain.entities.broker_flow import BrokerSummary
from src.domain.ports.broker_data_provider import (
    BrokerDataProvider,
    BrokerDataProviderError,
)

logger = logging.getLogger(__name__)

# API Configuration
IDX_API_BASE = "https://www.idx.co.id/primary/TradingSummary"
STOCK_SUMMARY_ENDPOINT = "/GetStockSummary"

# IDX standard lot size
SHARES_PER_LOT = 100

# Rate limiting - be respectful to IDX servers
REQUEST_DELAY_SECONDS = 1.0

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # Exponential backoff: 2s, 4s, 8s

# Browser-like headers required by IDX
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


class IdxBrokerDataProvider(BrokerDataProvider):
    """
    IDX (idx.co.id) broker data provider.

    Public API - no authentication required.
    Fetches per-stock foreign flow data from IDX's GetStockSummary endpoint.

    Provides:
    - Foreign buy/sell lots (exact from API)
    - Foreign buy/sell values (estimated: volume * closing price)
    - Total trading value and volume

    Does NOT provide:
    - Per-broker breakdown (top buyers/sellers)
    - Exact foreign flow values in IDR

    Example usage:
        provider = IdxBrokerDataProvider()
        summary = provider.fetch_broker_summary("BBCA", date(2025, 1, 24))
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._last_request_time: float = 0

    def is_authenticated(self) -> bool:
        """Public API - always available."""
        return True

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, target_date: date) -> dict[str, Any]:
        """
        Fetch stock summary for a given date from IDX API.

        Args:
            target_date: Trading date to fetch.

        Returns:
            JSON response as dict.

        Raises:
            BrokerDataProviderError: If request fails after retries.
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

                    if response.status_code == 429:
                        wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            "IDX rate limited (429), waiting %.1fs before retry %d/%d",
                            wait, attempt + 1, MAX_RETRIES,
                        )
                        time.sleep(wait)
                        continue

                    if response.status_code == 403:
                        # IDX returns 403 for non-trading days (holidays).
                        # Treat as empty data, not an error.
                        logger.debug(
                            "IDX returned 403 for %s (likely non-trading day)",
                            target_date,
                        )
                        return {"data": [], "recordsTotal": 0}

                    if response.status_code >= 500:
                        wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            "IDX server error (%d), waiting %.1fs before retry %d/%d",
                            response.status_code, wait, attempt + 1, MAX_RETRIES,
                        )
                        time.sleep(wait)
                        last_error = BrokerDataProviderError(
                            f"IDX API server error: {response.status_code}"
                        )
                        continue

                    if response.status_code != 200:
                        raise BrokerDataProviderError(
                            f"IDX API error: {response.status_code}"
                        )

                    return response.json()

            except httpx.TimeoutException as e:
                last_error = BrokerDataProviderError(f"IDX request timeout: {e}")
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "IDX timeout, waiting %.1fs before retry %d/%d",
                        wait, attempt + 1, MAX_RETRIES,
                    )
                    time.sleep(wait)
            except httpx.RequestError as e:
                last_error = BrokerDataProviderError(f"IDX request failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    time.sleep(wait)

        raise last_error or BrokerDataProviderError("IDX request failed after retries")

    def _parse_stock_summary(
        self,
        data: dict[str, Any],
    ) -> BrokerSummary:
        """
        Parse a single stock's data from IDX GetStockSummary response.

        Foreign flow values are estimated as volume * closing price,
        since IDX only provides volumes (in shares), not values.

        Args:
            data: Single stock record from IDX API response.

        Returns:
            BrokerSummary entity.
        """
        ticker = data["StockCode"]
        date_str = data["Date"][:10]  # "2025-01-24T00:00:00" -> "2025-01-24"
        trading_date = date.fromisoformat(date_str)

        # Foreign flow in shares (not lots)
        foreign_buy_shares = int(data.get("ForeignBuy", 0))
        foreign_sell_shares = int(data.get("ForeignSell", 0))

        # Convert to lots (IDX standard: 100 shares per lot)
        foreign_buy_lot = foreign_buy_shares // SHARES_PER_LOT
        foreign_sell_lot = foreign_sell_shares // SHARES_PER_LOT

        # Estimate foreign values using closing price
        # This is an approximation since actual transaction prices vary
        close_price = Decimal(str(data.get("Close", 0)))
        foreign_buy_value = Decimal(str(foreign_buy_shares)) * close_price
        foreign_sell_value = Decimal(str(foreign_sell_shares)) * close_price

        # Total market data
        total_value = Decimal(str(data.get("Value", 0)))
        total_volume_shares = int(data.get("Volume", 0))
        total_lot = total_volume_shares // SHARES_PER_LOT

        return BrokerSummary(
            ticker=ticker,
            date=trading_date,
            top_buyers=(),  # IDX API doesn't provide per-broker breakdown
            top_sellers=(),
            foreign_buy_value=foreign_buy_value,
            foreign_sell_value=foreign_sell_value,
            foreign_buy_lot=foreign_buy_lot,
            foreign_sell_lot=foreign_sell_lot,
            total_value=total_value,
            total_lot=total_lot,
        )

    def _find_stock_in_response(
        self,
        response_data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any] | None:
        """Find a specific stock in the API response data list."""
        ticker_upper = ticker.upper()
        for item in response_data.get("data", []):
            if item.get("StockCode") == ticker_upper:
                return item
        return None

    def fetch_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        """
        Fetch broker summary for a single date.

        Calls IDX GetStockSummary for the full market on target_date,
        then filters for the requested ticker.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA').
            target_date: The trading date to fetch.

        Returns:
            BrokerSummary if data available, None otherwise.
        """
        response = self._make_request(target_date)
        stock_data = self._find_stock_in_response(response, ticker)

        if not stock_data:
            return None

        return self._parse_stock_summary(stock_data)

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        """
        Fetch broker summaries for a date range.

        IDX API is per-date, so this iterates through each day.
        Weekends are skipped. Rate limiting is applied between requests.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA').
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            List of BrokerSummary entities, sorted by date ascending.
        """
        summaries: list[BrokerSummary] = []
        current_date = start_date

        while current_date <= end_date:
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            try:
                summary = self.fetch_broker_summary(ticker, current_date)
                if summary:
                    summaries.append(summary)
                    logger.debug("Fetched %s for %s", ticker, current_date)
            except BrokerDataProviderError as e:
                logger.warning(
                    "Failed to fetch %s for %s: %s",
                    ticker, current_date, e,
                )
                # Continue to next date - don't fail entire range for one day

            current_date += timedelta(days=1)

        # Already in order since we iterate chronologically
        return summaries
