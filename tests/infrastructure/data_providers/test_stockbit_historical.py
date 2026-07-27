"""Tests for StockbitHistoricalProvider and FallbackMarketDataProvider."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.entities.candle import Candle
from src.infrastructure.data_providers.fallback_provider import (
    FallbackMarketDataProvider,
    _expected_trading_days,
)
from src.infrastructure.data_providers.stockbit_historical import (
    StockbitHistoricalProvider,
    _parse_decimal,
    _parse_ohlcv_rows,
)

# ── Parser unit tests ─────────────────────────────────────────────────────────


def _make_row(d="2026-06-19", open_=6050, high=6300, low=6050, close=6300, volume=3665955) -> dict:
    return {
        "date": d,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,  # in LOTS
    }


def test_parse_ohlcv_rows_basic():
    rows = [_make_row()]
    candles = _parse_ohlcv_rows("BBCA", rows)
    assert len(candles) == 1
    c = candles[0]
    assert c.ticker == "BBCA"
    assert c.date == date(2026, 6, 19)
    assert c.open == Decimal("6050")
    assert c.high == Decimal("6300")
    assert c.low == Decimal("6050")
    assert c.close == Decimal("6300")
    assert c.volume == 3665955 * 100  # lots → shares


def test_parse_ohlcv_rows_sorted_ascending():
    rows = [_make_row("2026-06-20"), _make_row("2026-06-18"), _make_row("2026-06-19")]
    candles = _parse_ohlcv_rows("BBCA", rows)
    dates = [c.date for c in candles]
    assert dates == sorted(dates)


def test_parse_ohlcv_rows_skips_missing_price():
    rows = [
        _make_row(),
        {"date": "2026-06-18", "open": None, "high": 100, "low": 90, "close": 95, "volume": 100},
    ]
    candles = _parse_ohlcv_rows("BBCA", rows)
    assert len(candles) == 1


def test_parse_ohlcv_rows_skips_bad_date():
    rows = [
        _make_row(),
        {"date": "not-a-date", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 100},
    ]
    candles = _parse_ohlcv_rows("BBCA", rows)
    assert len(candles) == 1


def test_parse_ohlcv_rows_skips_non_dict():
    rows = [_make_row(), "garbage", None, 42]
    candles = _parse_ohlcv_rows("BBCA", rows)
    assert len(candles) == 1


def test_parse_ohlcv_rows_empty():
    assert _parse_ohlcv_rows("BBCA", []) == []


# ── _parse_decimal ────────────────────────────────────────────────────────────


def test_parse_decimal_float_is_rounded_to_3dp():
    """Stockbit returns Python floats for in-progress sessions; must not store
    IEEE 754 binary noise (e.g. 5737.73583984375 instead of 5737.736)."""
    result = _parse_decimal(5737.73583984375)
    assert result == Decimal("5737.736")


def test_parse_decimal_string_is_preserved_as_is():
    """String values from the API (settled sessions) must not be rounded."""
    result = _parse_decimal("5737.736")
    assert result == Decimal("5737.736")


def test_parse_decimal_integer_string_preserved():
    result = _parse_decimal("6300")
    assert result == Decimal("6300")


def test_parse_decimal_none_returns_none():
    assert _parse_decimal(None) is None


def test_parse_ohlcv_rows_float_prices_are_rounded(monkeypatch):
    """When Stockbit returns float OHLCV values, stored candles must have
    at most 3 decimal places — no IEEE 754 binary noise."""
    row = {
        "date": "2026-07-01",
        "open": 5640.61083984375,  # float with binary noise
        "high": 5737.73583984375,
        "low": 5607.451171875,
        "close": 5695.1162109375,
        "volume": 172115099,
    }
    candles = _parse_ohlcv_rows("IHSG", [row])
    assert len(candles) == 1
    c = candles[0]
    assert c.open == Decimal("5640.611")
    assert c.high == Decimal("5737.736")
    assert c.low == Decimal("5607.451")
    assert c.close == Decimal("5695.116")


# ── StockbitHistoricalProvider ────────────────────────────────────────────────


def test_returns_empty_when_no_broker_provider():
    prov = StockbitHistoricalProvider(api_client=None)
    result = prov.fetch_daily_ohlcv("BBCA", date(2026, 1, 1), date(2026, 6, 1))
    assert result == []


def test_provider_metadata():
    prov = StockbitHistoricalProvider(api_client=None)
    assert prov.provider_name == "stockbit"
    assert prov.volume_unit == "shares"
    assert prov.price_adjustment_policy == "raw"


def test_stockbit_provider_normalizes_yahoo_index_alias_to_ihsg():
    requested_urls: list[str] = []

    class FakeClient:
        def get(self, url, params=None):
            requested_urls.append(url)
            return {
                "data": {
                    "result": [
                        _make_row(
                            d="2026-07-01",
                            open_=5640.611,
                            high=5737.736,
                            low=5607.451,
                            close=5695.116,
                            volume=172115099,
                        )
                    ]
                }
            }

    prov = StockbitHistoricalProvider(api_client=FakeClient())
    candles = prov.fetch_daily_ohlcv("^JKSE", date(2026, 7, 1), date(2026, 7, 1))

    assert len(candles) == 1
    assert candles[0].ticker == "IHSG"
    assert candles[0].volume == 172115099 * 100
    assert "/historical/summary/IHSG?" in requested_urls[0]


# ── _expected_trading_days ────────────────────────────────────────────────────


def test_expected_trading_days_one_week():
    start = date(2026, 6, 15)  # Monday
    end = date(2026, 6, 19)  # Friday
    result = _expected_trading_days(start, end)
    assert result == 4  # 5 days * 5/7 ≈ 3.57 → round to 4


def test_expected_trading_days_same_day():
    d = date(2026, 6, 19)
    assert _expected_trading_days(d, d) >= 1


# ── FallbackMarketDataProvider ────────────────────────────────────────────────


def _candle(d: str, ticker: str = "BBCA") -> Candle:
    return Candle(
        ticker=ticker,
        date=date.fromisoformat(d),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
    )


def test_uses_primary_when_coverage_sufficient():
    primary = MagicMock()
    primary.fetch_daily_ohlcv.return_value = [_candle(f"2026-06-{d:02d}") for d in range(1, 25)]
    fallback = MagicMock()
    fallback.fetch_daily_ohlcv.return_value = []

    provider = FallbackMarketDataProvider(primary, fallback)
    result = provider.fetch_daily_ohlcv("BBCA", date(2026, 6, 1), date(2026, 6, 30))

    assert len(result) == 24
    fallback.fetch_daily_ohlcv.assert_not_called()


def test_uses_fallback_when_primary_empty():
    primary = MagicMock()
    primary.fetch_daily_ohlcv.return_value = []
    fallback = MagicMock()
    fallback.fetch_daily_ohlcv.return_value = [_candle("2026-06-19")]
    fallback.provider_name = "stockbit"
    fallback.volume_unit = "shares"
    fallback.price_adjustment_policy = "raw"

    provider = FallbackMarketDataProvider(primary, fallback, coverage_threshold=0.6)
    result = provider.fetch_daily_ohlcv("BBCA", date(2026, 6, 1), date(2026, 6, 30))

    assert len(result) == 1
    fallback.fetch_daily_ohlcv.assert_called_once()
    assert provider.provider_name == "stockbit"


def test_returns_primary_partial_when_fallback_also_empty():
    primary = MagicMock()
    primary.fetch_daily_ohlcv.return_value = [_candle("2026-06-19")]
    primary.provider_name = "yahoo"
    primary.volume_unit = "shares"
    primary.price_adjustment_policy = "yfinance_default"
    fallback = MagicMock()
    fallback.fetch_daily_ohlcv.return_value = []

    provider = FallbackMarketDataProvider(primary, fallback, coverage_threshold=0.9)
    result = provider.fetch_daily_ohlcv("BBCA", date(2026, 6, 1), date(2026, 6, 30))

    assert len(result) == 1
    assert provider.provider_name == "yahoo"


def test_primary_exception_triggers_fallback():
    primary = MagicMock()
    primary.fetch_daily_ohlcv.side_effect = Exception("Yahoo is down")
    fallback = MagicMock()
    fallback.fetch_daily_ohlcv.return_value = [_candle("2026-06-19")]
    fallback.provider_name = "stockbit"
    fallback.volume_unit = "shares"
    fallback.price_adjustment_policy = "raw"

    provider = FallbackMarketDataProvider(primary, fallback)
    result = provider.fetch_daily_ohlcv("BBCA", date(2026, 6, 1), date(2026, 6, 30))

    assert len(result) == 1
    assert provider.provider_name == "stockbit"
