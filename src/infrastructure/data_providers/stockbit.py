"""
Stockbit broker data provider.

Fetches broker summary and foreign flow data from Stockbit's API.
Requires JWT authentication token obtained from browser session.

Layer: Infrastructure
Depends on: Domain ports, httpx

Token acquisition:
1. Login to stockbit.com in browser
2. Open DevTools (F12) → Network tab
3. Click any stock ticker
4. Filter for "exodus" requests
5. Copy the Bearer token from Authorization header

Token validity: ~24 hours
"""

import json
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from src.domain.entities.broker_flow import (
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProvider,
    BrokerDataProviderError,
)


# API Configuration
STOCKBIT_API_BASE = "https://exodus.stockbit.com/api"
BROKER_SUMMARY_ENDPOINT = "/marketdetectors/{ticker}"

# Rate limiting
REQUEST_DELAY_SECONDS = 0.5

# Default paths
DEFAULT_TOKEN_PATH = Path.home() / ".ai-saham" / "stockbit_token.json"


class StockbitBrokerDataProvider(BrokerDataProvider):
    """
    Stockbit API client for broker flow data.

    Uses undocumented Stockbit API endpoints.
    Requires valid JWT token from authenticated browser session.

    Example usage:
        provider = StockbitBrokerDataProvider(token="eyJhbGci...")
        summary = provider.fetch_broker_summary("BBCA", date.today())
    """

    def __init__(
        self,
        token: str | None = None,
        token_path: Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize Stockbit provider.

        Args:
            token: JWT bearer token (takes precedence)
            token_path: Path to token file (fallback if token not provided)
            timeout: HTTP request timeout in seconds
        """
        self._token: str | None = token
        self._token_path = token_path or DEFAULT_TOKEN_PATH
        self._timeout = timeout
        self._last_request_time: float = 0

        # Load token from file if not provided
        if not self._token:
            self._load_token_from_file()

    def _load_token_from_file(self) -> None:
        """Load token from JSON file."""
        if self._token_path.exists():
            try:
                with open(self._token_path) as f:
                    data = json.load(f)
                    self._token = data.get("token")
            except (json.JSONDecodeError, OSError):
                pass

    def save_token(self, token: str) -> None:
        """
        Save token to file for persistence.

        Args:
            token: JWT bearer token to save
        """
        self._token = token
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._token_path, "w") as f:
            json.dump({"token": token, "saved_at": date.today().isoformat()}, f)

    def is_authenticated(self) -> bool:
        """Check if provider has a token configured."""
        return bool(self._token)

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers with authentication."""
        if not self._token:
            raise BrokerDataAuthError(
                "No Stockbit token configured. "
                "Use 'saham broker auth <token>' to set your token."
            )
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "ai-saham/1.0",
        }

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _make_request(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """
        Make API request to Stockbit.

        Args:
            ticker: Stock ticker (without .JK suffix)
            start_date: Start date for data range
            end_date: End date for data range

        Returns:
            JSON response as dict

        Raises:
            BrokerDataAuthError: If token is invalid or expired
            BrokerDataProviderError: If request fails
        """
        self._rate_limit()

        url = f"{STOCKBIT_API_BASE}{BROKER_SUMMARY_ENDPOINT.format(ticker=ticker.upper())}"
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "transaction_type": "TRANSACTION_TYPE_NET",
            "market_board": "MARKET_BOARD_REGULER",
            "investor_type": "INVESTOR_TYPE_ALL",
            "limit": 100,
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

                if response.status_code == 401:
                    raise BrokerDataAuthError(
                        "Stockbit token expired or invalid. "
                        "Please get a new token from stockbit.com"
                    )

                if response.status_code == 403:
                    raise BrokerDataAuthError(
                        "Access forbidden. Token may have insufficient permissions."
                    )

                if response.status_code != 200:
                    raise BrokerDataProviderError(
                        f"Stockbit API error: {response.status_code} - {response.text}"
                    )

                return response.json()

        except httpx.TimeoutException as e:
            raise BrokerDataProviderError(f"Request timeout: {e}") from e
        except httpx.RequestError as e:
            raise BrokerDataProviderError(f"Request failed: {e}") from e

    def _parse_broker_type(self, type_str: str | None) -> BrokerType:
        """Parse broker type from API response."""
        if not type_str:
            return BrokerType.UNKNOWN
        type_upper = type_str.upper()
        if "ASING" in type_upper or "FOREIGN" in type_upper:
            return BrokerType.FOREIGN
        if "LOKAL" in type_upper or "LOCAL" in type_upper or "DOMESTIC" in type_upper:
            return BrokerType.LOCAL
        return BrokerType.UNKNOWN

    def _parse_broker_transaction(self, data: dict[str, Any]) -> BrokerTransaction:
        """Parse broker transaction from API response."""
        return BrokerTransaction(
            broker_code=data.get("broker_code", data.get("code", "")),
            broker_name=data.get("broker_name", data.get("name", "")),
            broker_type=self._parse_broker_type(data.get("broker_type")),
            buy_lot=int(data.get("buy_lot", 0)),
            sell_lot=int(data.get("sell_lot", 0)),
            buy_value=Decimal(str(data.get("buy_value", 0))),
            sell_value=Decimal(str(data.get("sell_value", 0))),
            avg_buy_price=Decimal(str(data.get("avg_buy_price", 0))),
            avg_sell_price=Decimal(str(data.get("avg_sell_price", 0))),
        )

    def _parse_broker_summary(
        self,
        ticker: str,
        trading_date: date,
        data: dict[str, Any],
    ) -> BrokerSummary:
        """Parse broker summary from API response."""
        # Parse top buyers and sellers
        top_buyers_data = data.get("top_buyers", data.get("buyers", []))
        top_sellers_data = data.get("top_sellers", data.get("sellers", []))

        top_buyers = tuple(
            self._parse_broker_transaction(b)
            for b in top_buyers_data[:10]
            if b.get("broker_code") or b.get("code")
        )
        top_sellers = tuple(
            self._parse_broker_transaction(s)
            for s in top_sellers_data[:10]
            if s.get("broker_code") or s.get("code")
        )

        # Extract foreign flow data
        foreign_data = data.get("foreign", data.get("foreign_flow", {}))

        return BrokerSummary(
            ticker=ticker.upper(),
            date=trading_date,
            top_buyers=top_buyers,
            top_sellers=top_sellers,
            foreign_buy_value=Decimal(str(foreign_data.get("buy_value", 0))),
            foreign_sell_value=Decimal(str(foreign_data.get("sell_value", 0))),
            foreign_buy_lot=int(foreign_data.get("buy_lot", 0)),
            foreign_sell_lot=int(foreign_data.get("sell_lot", 0)),
            total_value=Decimal(str(data.get("total_value", 0))),
            total_lot=int(data.get("total_lot", 0)),
        )

    def fetch_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        """
        Fetch broker summary for a single date.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA')
            target_date: The trading date to fetch

        Returns:
            BrokerSummary if data available, None otherwise.
        """
        response = self._make_request(ticker, target_date, target_date)

        # Handle different response structures
        data_list = response.get("data", response.get("result", []))

        if not data_list:
            return None

        # API may return list or single item
        if isinstance(data_list, list):
            if not data_list:
                return None
            data = data_list[0]
        else:
            data = data_list

        return self._parse_broker_summary(ticker, target_date, data)

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        """
        Fetch broker summaries for a date range.

        Args:
            ticker: Stock ticker symbol (e.g., 'BBCA')
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of BrokerSummary entities, sorted by date ascending.
        """
        # Fetch in chunks to handle large date ranges
        summaries: list[BrokerSummary] = []
        current_date = start_date

        while current_date <= end_date:
            # Fetch up to 30 days at a time
            chunk_end = min(current_date + timedelta(days=30), end_date)

            response = self._make_request(ticker, current_date, chunk_end)
            data_list = response.get("data", response.get("result", []))

            if isinstance(data_list, list):
                for item in data_list:
                    # Extract date from item
                    item_date_str = item.get("date", item.get("trading_date"))
                    if item_date_str:
                        item_date = date.fromisoformat(item_date_str[:10])
                        summary = self._parse_broker_summary(ticker, item_date, item)
                        summaries.append(summary)

            current_date = chunk_end + timedelta(days=1)

        # Sort by date ascending
        summaries.sort(key=lambda s: s.date)
        return summaries


def validate_token(token: str, timeout: float = 10.0) -> bool:
    """
    Validate if a Stockbit token is still valid.

    Makes a test request to check token validity.

    Args:
        token: JWT bearer token to validate
        timeout: Request timeout in seconds

    Returns:
        True if token is valid, False otherwise
    """
    try:
        provider = StockbitBrokerDataProvider(token=token, timeout=timeout)
        # Try to fetch today's data for a common stock
        provider.fetch_broker_summary("BBCA", date.today())
        return True
    except BrokerDataAuthError:
        return False
    except BrokerDataProviderError:
        # Other errors (network, etc.) don't mean token is invalid
        return True
