"""Tests for StockbitEarningsProvider parser and cache logic."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.domain.value_objects.earnings_record import EarningsRecord
from src.infrastructure.browser.stockbit_earnings import (
    StockbitEarningsProvider,
    _next_prev_period,
    _parse_float,
    _parse_period_record,
)


# ── Parser unit tests ──────────────────────────────────────────────────────────

def _make_body(
    actual="119.12", estimate="-", surprise="-",
    yoy_change="3.81", prev_year="114.75",
    prev_q="4", prev_y="2025",
) -> dict:
    return {
        "data": {
            "quarter": 1, "year": "2026",
            "prev_earnings_period": {"quarter": prev_q, "year": prev_y},
            "next_earnings_period": {"quarter": "", "year": ""},
            "company": [{
                "company_name": "BBCA",
                "analyst": {
                    "consensus": {"actual": actual, "estimate": estimate, "surprise": surprise},
                    "prevyear": {"actual": actual, "change": yoy_change, "previous": prev_year},
                },
            }],
        }
    }


def test_parse_float_dash_returns_none():
    assert _parse_float("-") is None
    assert _parse_float("") is None
    assert _parse_float(None) is None


def test_parse_float_numeric_string():
    assert _parse_float("119.12") == pytest.approx(119.12)
    assert _parse_float("3.81") == pytest.approx(3.81)


def test_parse_period_record_no_estimate():
    record = _parse_period_record("BBCA", 1, 2026, _make_body())
    assert record is not None
    assert record.ticker == "BBCA"
    assert record.year == 2026
    assert record.quarter == 1
    assert record.eps_actual == pytest.approx(119.12)
    assert record.eps_estimate is None
    assert record.eps_surprise_pct is None
    assert record.eps_prev_year == pytest.approx(114.75)
    assert record.eps_yoy_change == pytest.approx(3.81)
    assert record.beat is None


def test_parse_period_record_with_estimate_beat():
    record = _parse_period_record("BBCA", 1, 2026, _make_body(
        actual="120.0", estimate="115.0", surprise="4.35",
    ))
    assert record is not None
    assert record.eps_estimate == pytest.approx(115.0)
    assert record.eps_surprise_pct == pytest.approx(4.35)
    assert record.beat is True


def test_parse_period_record_with_estimate_miss():
    record = _parse_period_record("BBCA", 1, 2026, _make_body(
        actual="110.0", estimate="120.0", surprise="-",  # surprise not given
    ))
    assert record is not None
    # surprise computed from actual vs estimate
    assert record.eps_surprise_pct == pytest.approx((110.0 - 120.0) / 120.0 * 100)
    assert record.beat is False


def test_parse_period_record_empty_company_returns_none():
    body = {"data": {"quarter": 1, "year": "2026", "company": []}}
    assert _parse_period_record("BBCA", 1, 2026, body) is None


def test_next_prev_period_returns_tuple():
    body = _make_body(prev_q="4", prev_y="2025")
    prev = _next_prev_period(body)
    assert prev == (4, 2025)


def test_next_prev_period_empty_returns_none():
    body = _make_body(prev_q="", prev_y="")
    assert _next_prev_period(body) is None


# ── EarningsRecord value object ───────────────────────────────────────────────

def test_earnings_record_label_no_estimate():
    r = EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=119.12, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=3.81, eps_prev_year=114.75,
    )
    assert "Q1 2026" in r.label
    assert "119.1" in r.label
    assert "no est." in r.label
    assert r.beat is None


def test_earnings_record_yoy_growth_pct():
    r = EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=119.12, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=3.81, eps_prev_year=114.75,
    )
    assert r.yoy_growth_pct == pytest.approx((119.12 - 114.75) / 114.75 * 100, rel=0.01)


def test_earnings_record_yoy_growth_none_when_no_prev():
    r = EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=119.12, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
    )
    assert r.yoy_growth_pct is None


# ── Cache round-trip ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_provider(tmp_path):
    return StockbitEarningsProvider(broker_provider=None, db_path=tmp_path / "test.db")


def test_schema_created(tmp_provider):
    with tmp_provider._get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='earnings_cache'"
        ).fetchone()
    assert row is not None


def test_write_then_read_single(tmp_provider):
    from datetime import datetime
    record = EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=119.12, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=3.81, eps_prev_year=114.75,
        fetched_at=datetime.now(),
    )
    tmp_provider._write_record(record)
    result = tmp_provider._read_cache_single("BBCA", 2026, 1)
    assert result is not None
    assert result.eps_actual == pytest.approx(119.12)
    assert result.eps_prev_year == pytest.approx(114.75)


def test_read_cache_returns_newest_first(tmp_provider):
    from datetime import datetime
    for q in [1, 2, 3]:
        tmp_provider._write_record(EarningsRecord(
            ticker="BBCA", year=2026, quarter=q,
            eps_actual=100.0 + q, eps_estimate=None, eps_surprise_pct=None,
            eps_yoy_change=None, eps_prev_year=None,
            fetched_at=datetime.now(),
        ))
    results = tmp_provider._read_cache("BBCA", quarters=4)
    assert len(results) == 3
    assert results[0].quarter == 3  # newest first
    assert results[1].quarter == 2
    assert results[2].quarter == 1


def test_is_cache_fresh_false_when_empty(tmp_provider):
    assert tmp_provider.is_cache_fresh("BBCA") is False


def test_get_earnings_history_returns_empty_without_provider(tmp_provider):
    result = tmp_provider.get_earnings_history("BBCA")
    assert result == []
