"""Tests for StockbitEarningsProvider parser and cache logic."""


import sqlite3
from datetime import date, datetime, timedelta

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
    return StockbitEarningsProvider(api_client=None, db_path=tmp_path / "test.db")


def test_schema_created(tmp_provider):
    with tmp_provider._get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='earnings_cache'"
        ).fetchone()
    assert row is not None


def test_legacy_primary_key_schema_rebuilds_to_pit_snapshots(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE earnings_cache (
                ticker TEXT NOT NULL,
                year INTEGER NOT NULL,
                quarter INTEGER NOT NULL,
                eps_actual REAL,
                eps_estimate REAL,
                eps_surprise_pct REAL,
                eps_yoy_change REAL,
                eps_prev_year REAL,
                fetched_date TEXT NOT NULL,
                PRIMARY KEY (ticker, year, quarter)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO earnings_cache
                (ticker, year, quarter, eps_actual, eps_estimate, eps_surprise_pct,
                 eps_yoy_change, eps_prev_year, fetched_date)
            VALUES ('BBCA', 2026, 1, 101.0, NULL, NULL, NULL, NULL, '2026-06-01T09:00:00')
            """
        )

    provider = StockbitEarningsProvider(api_client=None, db_path=db_path)

    with provider._get_conn() as conn:
        pk_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(earnings_cache)")
            if int(row["pk"]) > 0
        }
    result = provider.get_earnings_history(
        "BBCA",
        quarters=4,
        as_of_date=date(2026, 6, 6),
    )

    assert pk_columns == set()
    assert len(result) == 1
    assert result[0].eps_actual == pytest.approx(101.0)


def test_write_then_read_single(tmp_provider):
    from datetime import datetime
    record = EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=119.12, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=3.81, eps_prev_year=114.75,
        fetched_at=datetime.now(),
    )
    tmp_provider._cache.write_record(record)
    result = tmp_provider._cache.read_single("BBCA", 2026, 1)
    assert result is not None
    assert result.eps_actual == pytest.approx(119.12)
    assert result.eps_prev_year == pytest.approx(114.75)


def test_read_cache_returns_newest_first(tmp_provider):
    for q in [1, 2, 3]:
        tmp_provider._cache.write_record(EarningsRecord(
            ticker="BBCA", year=2026, quarter=q,
            eps_actual=100.0 + q, eps_estimate=None, eps_surprise_pct=None,
            eps_yoy_change=None, eps_prev_year=None,
            fetched_at=datetime.now(),
        ))
    results = tmp_provider._cache.read("BBCA")
    assert len(results) == 3
    assert results[0].quarter == 3  # newest first
    assert results[1].quarter == 2
    assert results[2].quarter == 1


def test_get_earnings_history_filters_future_fetched_rows_for_as_of_date(tmp_provider):
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=101.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime(2026, 6, 1, 9),
    ))
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=2,
        eps_actual=102.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime(2026, 6, 10, 9),
    ))

    results = tmp_provider.get_earnings_history(
        "BBCA",
        quarters=4,
        as_of_date=date(2026, 6, 6),
    )

    assert len(results) == 1
    assert results[0].quarter == 1


def test_get_earnings_history_keeps_multiple_snapshots_per_quarter(tmp_provider):
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=101.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime(2026, 6, 1, 9),
    ))
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=111.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime(2026, 6, 10, 9),
    ))

    prior = tmp_provider.get_earnings_history(
        "BBCA",
        quarters=4,
        as_of_date=date(2026, 6, 6),
    )
    latest = tmp_provider.get_earnings_history(
        "BBCA",
        quarters=4,
        as_of_date=date(2026, 6, 12),
    )

    assert len(prior) == 1
    assert prior[0].eps_actual == pytest.approx(101.0)
    assert len(latest) == 1
    assert latest[0].eps_actual == pytest.approx(111.0)


def test_get_earnings_history_returns_empty_when_no_prior_fetched_row(tmp_provider):
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=2,
        eps_actual=102.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime(2026, 6, 10, 9),
    ))

    results = tmp_provider.get_earnings_history(
        "BBCA",
        quarters=4,
        as_of_date=date(2026, 6, 6),
    )

    assert results == []


def test_is_cache_fresh_false_when_empty(tmp_provider):
    assert tmp_provider.is_cache_fresh("BBCA") is False


def test_is_cache_fresh_true_when_latest_available_history_snapshot_is_recent(tmp_provider):
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=101.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime.now(),
    ))

    assert tmp_provider.is_cache_fresh("BBCA") is True


def test_is_cache_fresh_false_when_latest_available_history_snapshot_is_stale(tmp_provider):
    tmp_provider._cache.write_record(EarningsRecord(
        ticker="BBCA", year=2026, quarter=1,
        eps_actual=101.0, eps_estimate=None, eps_surprise_pct=None,
        eps_yoy_change=None, eps_prev_year=None,
        fetched_at=datetime.now() - timedelta(days=8),
    ))

    assert tmp_provider.is_cache_fresh("BBCA") is False


def test_get_earnings_history_returns_empty_without_provider(tmp_provider):
    result = tmp_provider.get_earnings_history("BBCA")
    assert result == []
