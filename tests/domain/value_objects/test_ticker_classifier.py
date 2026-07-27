"""Tests for ticker classification domain service."""

from src.domain.value_objects.ticker_classifier import is_non_idx_ticker


def test_is_non_idx_ticker_indices():
    assert is_non_idx_ticker("^VIX") is True
    assert is_non_idx_ticker("^DJI") is True
    assert is_non_idx_ticker("^JKSE") is True


def test_is_non_idx_ticker_currencies():
    assert is_non_idx_ticker("IDR=X") is True
    assert is_non_idx_ticker("USDIDR=X") is True


def test_is_non_idx_ticker_futures():
    assert is_non_idx_ticker("KO=F") is True
    assert is_non_idx_ticker("MTF=F") is True


def test_is_non_idx_ticker_specific_global_tickers():
    assert is_non_idx_ticker("EIDO") is False
    assert is_non_idx_ticker("EIDO", {"EIDO"}) is True
    assert is_non_idx_ticker("eido", {"EIDO"}) is True
    assert is_non_idx_ticker("SPY", {"SPY"}) is True


def test_is_non_idx_ticker_idx_stocks_are_false():
    assert is_non_idx_ticker("BBCA") is False
    assert is_non_idx_ticker("BBRI") is False
    assert (
        is_non_idx_ticker("IHSG") is False
    )  # benchmark alias is application benchmark, not global index
    assert is_non_idx_ticker("ASII") is False
