"""Tests for Yahoo Finance market data provider ticker normalization."""

from src.infrastructure.data_providers.yahoo import YahooFinanceProvider


def test_yahoo_provider_appends_idx_suffix_to_plain_stock_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("BBCA") == "BBCA.JK"


def test_yahoo_provider_preserves_index_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("^JKSE") == "^JKSE"


def test_yahoo_provider_preserves_qualified_ticker():
    provider = YahooFinanceProvider()

    assert provider._to_yahoo_ticker("BBCA.JK") == "BBCA.JK"
