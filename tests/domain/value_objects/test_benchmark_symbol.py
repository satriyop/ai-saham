from src.domain.value_objects import (
    CANONICAL_BENCHMARK_TICKER,
    YAHOO_IHSG_TICKER,
    canonicalize_ticker,
    is_benchmark_ticker,
)


def test_canonicalize_ticker_maps_benchmark_aliases_to_ihsg():
    assert canonicalize_ticker("IHSG") == CANONICAL_BENCHMARK_TICKER
    assert canonicalize_ticker("^JKSE") == CANONICAL_BENCHMARK_TICKER
    assert canonicalize_ticker("bbca") == "BBCA"


def test_is_benchmark_ticker_accepts_canonical_and_yahoo_alias():
    assert is_benchmark_ticker(CANONICAL_BENCHMARK_TICKER) is True
    assert is_benchmark_ticker(YAHOO_IHSG_TICKER) is True
    assert is_benchmark_ticker("BBCA") is False
