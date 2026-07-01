"""Tests for Yahoo Finance market data provider ticker normalization and volume handling."""

import pandas as pd
import pytest
from datetime import date
from decimal import Decimal

from src.infrastructure.data_providers.yahoo import YahooFinanceProvider


# ── Ticker normalization ───────────────────────────────────────────────────────

def test_yahoo_provider_appends_idx_suffix_to_plain_stock_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("BBCA") == "BBCA.JK"


def test_yahoo_provider_preserves_index_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("^JKSE") == "^JKSE"


def test_yahoo_provider_maps_canonical_ihsg_to_yahoo_index_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("IHSG") == "^JKSE"


def test_yahoo_provider_preserves_qualified_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("BBCA.JK") == "BBCA.JK"


def test_yahoo_provider_exposes_candle_provenance_metadata():
    provider = YahooFinanceProvider()

    assert provider.provider_name == "yahoo"
    assert provider.volume_unit == "shares"
    assert provider.price_adjustment_policy == "yfinance_default"


# ── Volume conversion helpers ─────────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal yfinance-style DataFrame for _dataframe_to_candles."""
    records = []
    index = []
    for r in rows:
        index.append(pd.Timestamp(r["date"]))
        records.append({
            "Open":   r["open"],
            "High":   r["high"],
            "Low":    r["low"],
            "Close":  r["close"],
            "Volume": r["volume"],
        })
    df = pd.DataFrame(records, index=pd.DatetimeIndex(index))
    df.index.name = "Date"
    return df


# ── IHSG volume: lots → shares conversion ────────────────────────────────────

def test_yahoo_ihsg_volume_is_multiplied_by_100():
    """Yahoo reports ^JKSE volume in lots. The stored value must be in shares
    (lots * 100) to be consistent with Stockbit and the volume_unit='shares' label."""
    provider = YahooFinanceProvider()
    df = _make_df([{
        "date": "2026-06-25",
        "open": 5873.07, "high": 6056.20, "low": 5864.00, "close": 5999.04,
        "volume": 187_930_400,   # Yahoo value — in lots
    }])

    candles = provider._dataframe_to_candles("IHSG", df)

    assert len(candles) == 1
    assert candles[0].volume == 187_930_400 * 100   # stored as shares


def test_yahoo_ihsg_zero_volume_row_is_skipped():
    """Yahoo returns volume=0 for ^JKSE when the session is in progress.
    That row must be dropped — a zero-volume IHSG daily bar is not valid."""
    provider = YahooFinanceProvider()
    df = _make_df([
        {"date": "2026-06-30", "open": 5801.0, "high": 5811.0, "low": 5638.0,
         "close": 5643.0, "volume": 177_538_200},
        {"date": "2026-07-01", "open": 5640.0, "high": 5737.0, "low": 5607.0,
         "close": 5695.0, "volume": 0},           # in-progress session
    ])

    candles = provider._dataframe_to_candles("IHSG", df)

    assert len(candles) == 1
    assert candles[0].date == date(2026, 6, 30)


def test_yahoo_stock_volume_is_not_multiplied():
    """Non-benchmark tickers must NOT have volume multiplied — Yahoo stock
    volume is already in shares."""
    provider = YahooFinanceProvider()
    df = _make_df([{
        "date": "2026-06-25",
        "open": 9400.0, "high": 9500.0, "low": 9350.0, "close": 9450.0,
        "volume": 12_345_678,
    }])

    candles = provider._dataframe_to_candles("BBCA", df)

    assert len(candles) == 1
    assert candles[0].volume == 12_345_678   # unchanged


def test_yahoo_stock_zero_volume_row_is_kept():
    """Zero volume for a regular stock (e.g. holiday, no trade) is valid
    and must not be dropped."""
    provider = YahooFinanceProvider()
    df = _make_df([{
        "date": "2026-06-25",
        "open": 9400.0, "high": 9400.0, "low": 9400.0, "close": 9400.0,
        "volume": 0,
    }])

    candles = provider._dataframe_to_candles("BBCA", df)

    assert len(candles) == 1
    assert candles[0].volume == 0
