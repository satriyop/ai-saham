"""Tests for exploratory fallback/search helpers — Stockbit pre-open JSON scanning."""

from decimal import Decimal

from src.infrastructure.browser.stockbit_preopen_json_search import (
    search_best_bid_in_api_responses,
    search_movers_in_api_responses,
)


def test_search_movers_in_api_responses_extracts_nested_ticker_and_iev():
    responses = [
        {
            "body": {
                "data": {
                    "result": [
                        {"symbol": "BBCA", "iev": 5_000_000},
                        {"ticker": "TLKM", "iev": 3_000_000},
                    ]
                }
            }
        }
    ]
    movers = search_movers_in_api_responses(responses, iev_min=1_000_000)
    tickers = {m.ticker for m in movers}
    assert tickers == {"BBCA", "TLKM"}


def test_search_movers_in_api_responses_filters_below_iev_min():
    responses = [
        {
            "body": {
                "movers": [
                    {"symbol": "BBRI", "iev": 500_000},
                    {"symbol": "ASII", "iev": 2_000_000},
                ]
            }
        }
    ]
    movers = search_movers_in_api_responses(responses, iev_min=1_000_000)
    assert [m.ticker for m in movers] == ["ASII"]


def test_search_best_bid_in_api_responses_finds_nested_bid_list():
    responses = [
        {
            "body": {
                "data": {
                    "bids": [
                        {"price": "4900", "volume": 100},
                    ]
                }
            }
        }
    ]
    bid = search_best_bid_in_api_responses(responses, ticker="BBCA")
    assert bid is not None
    assert bid.price == Decimal("4900")
    assert bid.volume == 100


def test_search_best_bid_in_api_responses_picks_highest_volume():
    responses = [
        {
            "body": {
                "bid": [
                    {"price": "4900", "volume": 100},
                    {"price": "4890", "volume": 5_000},
                    {"price": "4880", "volume": 2_000},
                ]
            }
        }
    ]
    bid = search_best_bid_in_api_responses(responses, ticker="BBCA")
    assert bid is not None
    assert bid.price == Decimal("4890")
    assert bid.volume == 5_000


def test_search_movers_in_api_responses_skips_invalid_bodies():
    responses = [
        {"body": "not a dict"},
        {},
        {"body": None},
    ]
    assert search_movers_in_api_responses(responses, iev_min=1_000_000) == []


def test_search_best_bid_in_api_responses_skips_invalid_bodies():
    responses = [
        {"body": "not a dict"},
        {},
        {"body": None},
    ]
    assert search_best_bid_in_api_responses(responses, ticker="BBCA") is None
