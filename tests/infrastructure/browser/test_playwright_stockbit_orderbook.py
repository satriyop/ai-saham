"""Tests for orderbook parser — both bid and offer sides."""

from decimal import Decimal

from src.infrastructure.browser.playwright_stockbit_provider import _parse_top_of_book


def _body(bid_price, bid_qty, offer_price, offer_qty):
    """Build a minimal iepiev.best_bid_offer response body."""
    return {
        "data": {
            "iepiev": {
                "best_bid_offer": {
                    "bid":   {"price": {"raw": bid_price},   "quantity": {"raw": bid_qty}},
                    "offer": {"price": {"raw": offer_price}, "quantity": {"raw": offer_qty}},
                }
            }
        }
    }


def test_parse_top_of_book_returns_both_sides():
    body = _body(5_000, 200, 5_025, 150)
    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
    assert bid_price == Decimal("5000")
    assert bid_lots == 200
    assert offer_price == Decimal("5025")
    assert offer_lots == 150


def test_parse_top_of_book_fallback_to_depth_arrays():
    """When iepiev block is absent, fall back to data.bid[]/data.offer[] arrays."""
    body = {
        "data": {
            "bid":   [{"price": "4900", "volume": 50_000}],
            "offer": [{"price": "4925", "volume": 30_000}],
        }
    }
    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
    assert bid_price == Decimal("4900")
    assert bid_lots == 500   # 50_000 shares ÷ 100
    assert offer_price == Decimal("4925")
    assert offer_lots == 300  # 30_000 shares ÷ 100


def test_parse_top_of_book_partial_data_offer_only():
    """Bid missing from iepiev → bid falls back to depth array; offer stays from iepiev."""
    body = {
        "data": {
            "iepiev": {
                "best_bid_offer": {
                    "bid":   {"price": {"raw": 0}, "quantity": {"raw": 0}},
                    "offer": {"price": {"raw": 5_025}, "quantity": {"raw": 150}},
                }
            },
            "bid": [{"price": "4_950", "volume": 20_000}],
        }
    }
    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
    # offer comes from iepiev (confirmed)
    assert offer_price == Decimal("5025")
    assert offer_lots == 150


def test_parse_top_of_book_empty_body_returns_nones():
    assert _parse_top_of_book(None) == (None, None, None, None)
    assert _parse_top_of_book({}) == (None, None, None, None)
    assert _parse_top_of_book({"data": {}}) == (None, None, None, None)
