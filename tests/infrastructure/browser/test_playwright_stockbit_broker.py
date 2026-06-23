"""Tests for Stockbit broker summary parsing — real vs synthetic total_value."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from src.infrastructure.browser.playwright_stockbit import (
    _fetch_historical_summary_totals,
    _parse_marketdetectors_response,
)


def _marketdetectors_body():
    """Minimal /marketdetectors response with 2 buyers and 1 seller."""
    return {
        "data": {
            "broker_summary": {
                "brokers_buy": [
                    {
                        "netbs_broker_code": "BK",
                        "blot": 1000,
                        "bval": 6275000000,
                        "netbs_buy_avg_price": 6275,
                        "type": "Asing",
                        "netbs_date": "20260618",
                    },
                    {
                        "netbs_broker_code": "ZP",
                        "blot": 500,
                        "bval": 3137500000,
                        "netbs_buy_avg_price": 6275,
                        "type": "Asing",
                        "netbs_date": "20260618",
                    },
                ],
                "brokers_sell": [
                    {
                        "netbs_broker_code": "YP",
                        "slot": -800,
                        "sval": -5020000000,
                        "netbs_sell_avg_price": 6275,
                        "type": "Lokal",
                        "netbs_date": "20260618",
                    },
                ],
            }
        }
    }


# synthetic total from the 3 broker rows above:
# BK: buy=6275000000, ZP: buy=3137500000, YP: sell=5020000000
# total_val = 6275000000 + 3137500000 + 5020000000 = 14432500000
_SYNTHETIC_TOTAL_VAL = Decimal("14432500000")
_SYNTHETIC_TOTAL_LOT = 1000 + 500 + 800  # 2300


def _historical_summary_body_single_day():
    """Minimal /company-price-feed/historical/summary response for one day."""
    return {
        "data": {
            "result": [
                {
                    "date": "2026-06-18",
                    "value": 1430146602500,
                    "volume": 2324893,
                    "close": 6075,
                }
            ]
        }
    }


def _historical_summary_body_two_days():
    return {
        "data": {
            "result": [
                {"date": "2026-06-17", "value": 2990187572500, "volume": 4674943},
                {"date": "2026-06-18", "value": 1430146602500, "volume": 2324893},
            ]
        }
    }


# ── _parse_marketdetectors_response tests ─────────────────────────────────────

def test_real_total_used_when_provided():
    real_total = (Decimal("1430146602500"), 2324893)
    summaries = _parse_marketdetectors_response(
        "BBCA", date(2026, 6, 18), _marketdetectors_body(), real_total=real_total
    )
    assert len(summaries) == 1
    s = summaries[0]
    assert s.total_value == Decimal("1430146602500")
    assert s.total_lot == 2324893


def test_synthetic_fallback_when_real_total_is_none():
    summaries = _parse_marketdetectors_response(
        "BBCA", date(2026, 6, 18), _marketdetectors_body(), real_total=None
    )
    assert len(summaries) == 1
    s = summaries[0]
    assert s.total_value == _SYNTHETIC_TOTAL_VAL
    assert s.total_lot == _SYNTHETIC_TOTAL_LOT


def test_real_total_is_larger_than_synthetic():
    real_total = (Decimal("1430146602500"), 2324893)
    summaries_real = _parse_marketdetectors_response(
        "BBCA", date(2026, 6, 18), _marketdetectors_body(), real_total=real_total
    )
    summaries_synth = _parse_marketdetectors_response(
        "BBCA", date(2026, 6, 18), _marketdetectors_body(), real_total=None
    )
    assert summaries_real[0].total_value > summaries_synth[0].total_value


def test_foreign_fields_unaffected_by_real_total():
    real_total = (Decimal("1430146602500"), 2324893)
    s_real = _parse_marketdetectors_response(
        "BBCA", date(2026, 6, 18), _marketdetectors_body(), real_total=real_total
    )[0]
    s_synth = _parse_marketdetectors_response(
        "BBCA", date(2026, 6, 18), _marketdetectors_body(), real_total=None
    )[0]
    # Foreign fields come from broker rows — must be identical regardless of total
    assert s_real.foreign_buy_value == s_synth.foreign_buy_value
    assert s_real.foreign_sell_value == s_synth.foreign_sell_value
    assert s_real.foreign_buy_lot == s_synth.foreign_buy_lot
    assert s_real.foreign_sell_lot == s_synth.foreign_sell_lot


# ── _fetch_historical_summary_totals tests ────────────────────────────────────

def test_fetch_totals_single_day():
    with patch(
        "src.infrastructure.browser.playwright_stockbit._exodus_get",
        return_value=_historical_summary_body_single_day(),
    ):
        result = _fetch_historical_summary_totals(
            "BBCA", date(2026, 6, 18), date(2026, 6, 18), token="fake"
        )
    assert result is not None
    total_value, total_lot = result
    assert total_value == Decimal("1430146602500")
    assert total_lot == 2324893


def test_fetch_totals_sums_multiple_days():
    with patch(
        "src.infrastructure.browser.playwright_stockbit._exodus_get",
        return_value=_historical_summary_body_two_days(),
    ):
        result = _fetch_historical_summary_totals(
            "BBCA", date(2026, 6, 17), date(2026, 6, 18), token="fake"
        )
    assert result is not None
    total_value, total_lot = result
    assert total_value == Decimal("2990187572500") + Decimal("1430146602500")
    assert total_lot == 4674943 + 2324893


def test_fetch_totals_returns_none_on_empty_response():
    with patch(
        "src.infrastructure.browser.playwright_stockbit._exodus_get",
        return_value=None,
    ):
        result = _fetch_historical_summary_totals(
            "BBCA", date(2026, 6, 18), date(2026, 6, 18), token="fake"
        )
    assert result is None


def test_fetch_totals_returns_none_on_empty_result_list():
    with patch(
        "src.infrastructure.browser.playwright_stockbit._exodus_get",
        return_value={"data": {"result": []}},
    ):
        result = _fetch_historical_summary_totals(
            "BBCA", date(2026, 6, 18), date(2026, 6, 18), token="fake"
        )
    assert result is None


def test_fetch_totals_returns_none_on_zero_value():
    with patch(
        "src.infrastructure.browser.playwright_stockbit._exodus_get",
        return_value={"data": {"result": [{"date": "2026-06-18", "value": 0, "volume": 100}]}},
    ):
        result = _fetch_historical_summary_totals(
            "BBCA", date(2026, 6, 18), date(2026, 6, 18), token="fake"
        )
    assert result is None
