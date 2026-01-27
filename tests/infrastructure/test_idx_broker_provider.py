"""
Tests for IdxBrokerDataProvider.

Tests:
- Response parsing (StockSummary → BrokerSummary)
- Stock filtering from market-wide response
- Rate limiting behavior
- Date range iteration (weekends skipped)
- Error handling (network, 403, 429, 5xx)
- Foreign flow value estimation
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.domain.ports.broker_data_provider import BrokerDataProviderError
from src.infrastructure.data_providers.idx import (
    IdxBrokerDataProvider,
    SHARES_PER_LOT,
)


# --- Fixtures ---

SAMPLE_STOCK_DATA = {
    "StockCode": "BBCA",
    "StockName": "Bank Central Asia Tbk.",
    "Date": "2025-01-24T00:00:00",
    "Previous": 9600.0,
    "OpenPrice": 9625.0,
    "High": 9650.0,
    "Low": 9350.0,
    "Close": 9350.0,
    "Change": -250.0,
    "Volume": 152057000.0,
    "Value": 1441026497500.0,
    "Frequency": 68041.0,
    "ForeignSell": 114861200.0,
    "ForeignBuy": 36724900.0,
    "ListedShares": 122042299500.0,
    "TradebleShares": 122042299500.0,
    "NonRegularVolume": 0.0,
    "NonRegularValue": 0.0,
    "NonRegularFrequency": 0.0,
}

SAMPLE_RESPONSE = {
    "draw": 0,
    "recordsTotal": 3,
    "recordsFiltered": 3,
    "data": [
        {
            "StockCode": "AADI",
            "Date": "2025-01-24T00:00:00",
            "Close": 9075.0,
            "Volume": 16629300.0,
            "Value": 151341517500.0,
            "ForeignSell": 1953700.0,
            "ForeignBuy": 3905200.0,
        },
        SAMPLE_STOCK_DATA,
        {
            "StockCode": "TLKM",
            "Date": "2025-01-24T00:00:00",
            "Close": 2700.0,
            "Volume": 50000000.0,
            "Value": 135000000000.0,
            "ForeignSell": 5000000.0,
            "ForeignBuy": 3000000.0,
        },
    ],
}


def _make_mock_response(status_code: int = 200, json_data: dict | None = None):
    """Create a mock httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = json_data or SAMPLE_RESPONSE
    mock.text = ""
    return mock


# --- Tests ---


class TestIdxBrokerDataProviderAuth:
    """Tests for authentication (public API)."""

    def test_is_always_authenticated(self):
        """Public API should always report authenticated."""
        provider = IdxBrokerDataProvider()
        assert provider.is_authenticated() is True


class TestParseStockSummary:
    """Tests for parsing IDX stock summary into BrokerSummary."""

    def test_parse_valid_stock_data(self):
        """Should correctly parse BBCA stock data into BrokerSummary."""
        provider = IdxBrokerDataProvider()
        summary = provider._parse_stock_summary(SAMPLE_STOCK_DATA)

        assert summary.ticker == "BBCA"
        assert summary.date == date(2025, 1, 24)

        # Foreign flow lots (shares / 100)
        assert summary.foreign_buy_lot == 36724900 // SHARES_PER_LOT
        assert summary.foreign_sell_lot == 114861200 // SHARES_PER_LOT

        # Foreign flow values (estimated: shares * close price)
        close = Decimal("9350")
        assert summary.foreign_buy_value == Decimal("36724900") * close
        assert summary.foreign_sell_value == Decimal("114861200") * close

        # Total market data
        assert summary.total_value == Decimal("1441026497500")
        assert summary.total_lot == 152057000 // SHARES_PER_LOT

        # Empty top buyers/sellers (IDX doesn't provide per-broker data)
        assert summary.top_buyers == ()
        assert summary.top_sellers == ()

    def test_foreign_net_flow_direction(self):
        """Should correctly compute net foreign flow direction."""
        provider = IdxBrokerDataProvider()
        summary = provider._parse_stock_summary(SAMPLE_STOCK_DATA)

        # ForeignSell > ForeignBuy → net selling
        assert summary.foreign_net_lot < 0
        assert summary.is_foreign_accumulating is False

    def test_parse_zero_foreign_flow(self):
        """Should handle stocks with zero foreign activity."""
        data = {
            "StockCode": "TINY",
            "Date": "2025-01-24T00:00:00",
            "Close": 50.0,
            "Volume": 1000.0,
            "Value": 50000.0,
            "ForeignSell": 0.0,
            "ForeignBuy": 0.0,
        }
        provider = IdxBrokerDataProvider()
        summary = provider._parse_stock_summary(data)

        assert summary.foreign_buy_lot == 0
        assert summary.foreign_sell_lot == 0
        assert summary.foreign_buy_value == Decimal("0")
        assert summary.foreign_sell_value == Decimal("0")

    def test_parse_missing_optional_fields(self):
        """Should handle missing optional fields with defaults."""
        data = {
            "StockCode": "TEST",
            "Date": "2025-01-24T00:00:00",
        }
        provider = IdxBrokerDataProvider()
        summary = provider._parse_stock_summary(data)

        assert summary.ticker == "TEST"
        assert summary.foreign_buy_lot == 0
        assert summary.total_value == Decimal("0")
        assert summary.total_lot == 0


class TestFindStockInResponse:
    """Tests for filtering stock from market-wide response."""

    def test_find_existing_stock(self):
        """Should find BBCA in response data."""
        provider = IdxBrokerDataProvider()
        result = provider._find_stock_in_response(SAMPLE_RESPONSE, "BBCA")
        assert result is not None
        assert result["StockCode"] == "BBCA"

    def test_find_stock_case_insensitive(self):
        """Should find stock regardless of input case."""
        provider = IdxBrokerDataProvider()
        result = provider._find_stock_in_response(SAMPLE_RESPONSE, "bbca")
        assert result is not None
        assert result["StockCode"] == "BBCA"

    def test_stock_not_found(self):
        """Should return None for non-existent stock."""
        provider = IdxBrokerDataProvider()
        result = provider._find_stock_in_response(SAMPLE_RESPONSE, "ZZZZ")
        assert result is None

    def test_empty_response_data(self):
        """Should return None when response has no data."""
        provider = IdxBrokerDataProvider()
        result = provider._find_stock_in_response({"data": []}, "BBCA")
        assert result is None


class TestFetchBrokerSummary:
    """Tests for single-date fetch."""

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_fetch_existing_stock(self, mock_client_cls):
        """Should fetch and parse broker summary for existing stock."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(200, SAMPLE_RESPONSE)

        provider = IdxBrokerDataProvider()
        summary = provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

        assert summary is not None
        assert summary.ticker == "BBCA"
        assert summary.date == date(2025, 1, 24)

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_fetch_nonexistent_stock_returns_none(self, mock_client_cls):
        """Should return None for stock not in response."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(200, SAMPLE_RESPONSE)

        provider = IdxBrokerDataProvider()
        summary = provider.fetch_broker_summary("ZZZZ", date(2025, 1, 24))

        assert summary is None


class TestFetchBrokerSummaries:
    """Tests for date range fetch."""

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_skips_weekends(self, mock_client_cls):
        """Should skip Saturday and Sunday dates."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(200, SAMPLE_RESPONSE)

        provider = IdxBrokerDataProvider()
        # 2025-01-20 (Mon) to 2025-01-26 (Sun) = 5 weekdays
        summaries = provider.fetch_broker_summaries(
            "BBCA", date(2025, 1, 20), date(2025, 1, 26)
        )

        # Should have called API 5 times (Mon-Fri), not 7
        assert mock_client.get.call_count == 5

    @patch("src.infrastructure.data_providers.idx.time.sleep")
    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_continues_on_single_day_failure(self, mock_client_cls, mock_sleep):
        """Should continue fetching if one day fails with a network error."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Day 1 (Mon): network error on all 3 retries
        # Day 2 (Tue): succeeds
        mock_client.get.side_effect = [
            httpx.ConnectError("connection refused"),
            httpx.ConnectError("connection refused"),
            httpx.ConnectError("connection refused"),
            _make_mock_response(200, SAMPLE_RESPONSE),
        ]

        provider = IdxBrokerDataProvider()
        # Mon-Tue (2 weekdays)
        summaries = provider.fetch_broker_summaries(
            "BBCA", date(2025, 1, 20), date(2025, 1, 21)
        )

        # Day 1 fails after retries, day 2 succeeds → 1 summary
        assert len(summaries) == 1
        assert summaries[0].ticker == "BBCA"

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_403_returns_no_data_in_range(self, mock_client_cls):
        """403 (holiday) should produce no summary, not an error."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Day 1: 403 (holiday), Day 2: normal data
        mock_client.get.side_effect = [
            _make_mock_response(403),
            _make_mock_response(200, SAMPLE_RESPONSE),
        ]

        provider = IdxBrokerDataProvider()
        summaries = provider.fetch_broker_summaries(
            "BBCA", date(2025, 1, 20), date(2025, 1, 21)
        )

        # Day 1 is holiday (403 → empty), day 2 has data → 1 summary
        assert len(summaries) == 1


class TestErrorHandling:
    """Tests for error scenarios."""

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_403_returns_none_for_non_trading_day(self, mock_client_cls):
        """Should return None on 403 (IDX returns 403 for holidays)."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(403)

        provider = IdxBrokerDataProvider()
        result = provider.fetch_broker_summary("BBCA", date(2025, 12, 31))

        # 403 is treated as "no data" (non-trading day), not an error
        assert result is None

    @patch("src.infrastructure.data_providers.idx.time.sleep")
    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_429_retries_with_backoff(self, mock_client_cls, mock_sleep):
        """Should retry on 429 with exponential backoff."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # 429 three times → exhausts retries
        mock_client.get.return_value = _make_mock_response(429)

        provider = IdxBrokerDataProvider()
        provider._last_request_time = 0  # Skip rate limit wait

        with pytest.raises(BrokerDataProviderError):
            provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

        assert mock_client.get.call_count == 3  # MAX_RETRIES

    @patch("src.infrastructure.data_providers.idx.time.sleep")
    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_5xx_retries_with_backoff(self, mock_client_cls, mock_sleep):
        """Should retry on 5xx server errors."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # 500 twice, then success
        mock_client.get.side_effect = [
            _make_mock_response(500),
            _make_mock_response(500),
            _make_mock_response(200, SAMPLE_RESPONSE),
        ]

        provider = IdxBrokerDataProvider()
        provider._last_request_time = 0

        summary = provider.fetch_broker_summary("BBCA", date(2025, 1, 24))
        assert summary is not None
        assert mock_client.get.call_count == 3

    @patch("src.infrastructure.data_providers.idx.time.sleep")
    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_timeout_retries(self, mock_client_cls, mock_sleep):
        """Should retry on timeout errors."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        provider = IdxBrokerDataProvider()
        provider._last_request_time = 0

        with pytest.raises(BrokerDataProviderError, match="timeout"):
            provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

        assert mock_client.get.call_count == 3  # MAX_RETRIES

    @patch("src.infrastructure.data_providers.idx.time.sleep")
    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_network_error_retries(self, mock_client_cls, mock_sleep):
        """Should retry on network errors."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        provider = IdxBrokerDataProvider()
        provider._last_request_time = 0

        with pytest.raises(BrokerDataProviderError, match="request failed"):
            provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_non_200_non_retryable_raises(self, mock_client_cls):
        """Should raise immediately for non-retryable status codes."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(404)

        provider = IdxBrokerDataProvider()

        with pytest.raises(BrokerDataProviderError, match="404"):
            provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

        # Should not retry for 404
        assert mock_client.get.call_count == 1


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    @patch("src.infrastructure.data_providers.idx.time.sleep")
    @patch("src.infrastructure.data_providers.idx.time.time")
    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_rate_limit_delays_between_requests(self, mock_client_cls, mock_time, mock_sleep):
        """Should delay when requests are too fast."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(200, SAMPLE_RESPONSE)

        # Simulate: first call at t=100, second call at t=100.3 (0.3s later)
        mock_time.side_effect = [100.0, 100.0, 100.3, 100.3]

        provider = IdxBrokerDataProvider()
        provider._last_request_time = 100.0  # Just made a request

        provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

        # Should have slept for ~0.7s (1.0 - 0.3)
        mock_sleep.assert_called()


class TestRequestParameters:
    """Tests for correct API request construction."""

    @patch("src.infrastructure.data_providers.idx.httpx.Client")
    def test_date_format_in_request(self, mock_client_cls):
        """Should format date as YYYYMMDD for IDX API."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _make_mock_response(200, SAMPLE_RESPONSE)

        provider = IdxBrokerDataProvider()
        provider.fetch_broker_summary("BBCA", date(2025, 1, 24))

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["date"] == "20250124"
        assert params["length"] == 9999
        assert params["start"] == 0
