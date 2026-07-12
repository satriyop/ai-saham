"""
Point-in-time enrichment tests for company_fundamentals and shareholding_composition.

These tests verify that after the multi-row PIT schema migration:
  - As-of lookups return the latest row whose fetch date is on or before as_of_date.
  - Lookups return None when no row exists before as_of_date (no look-ahead bias).
  - The PIT market_cap_idr from the provider feeds through TickerProfileClassifier
    to produce a non-UNKNOWN tp_market_cap_bucket (application-level chain test).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider


@pytest.fixture
def fundamentals_db(tmp_path):
    db = tmp_path / "test.db"
    StockbitFundamentalsProvider(api_client=None, db_path=db)
    # Pre-populate two PIT rows
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO company_fundamentals "
            "(ticker, fetched_date, market_cap_idr, piotroski_f_score) VALUES (?,?,?,?)",
            ("BBCA", "2026-05-01", 500_000_000_000_000, 7),
        )
        conn.execute(
            "INSERT OR REPLACE INTO company_fundamentals "
            "(ticker, fetched_date, market_cap_idr, piotroski_f_score) VALUES (?,?,?,?)",
            ("BBCA", "2026-07-01", 1_000_000_000_000_000, 8),
        )
    return db


@pytest.fixture
def shareholding_db(tmp_path):
    db = tmp_path / "test.db"
    StockbitShareholdingProvider(api_client=None, db_path=db)
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO shareholding_composition "
            "(ticker, fetched_date, report_date, institution_pct) VALUES (?,?,?,?)",
            ("BBCA", "2026-05-10", "2026-05-01", 65.0),
        )
        conn.execute(
            "INSERT OR REPLACE INTO shareholding_composition "
            "(ticker, fetched_date, report_date, institution_pct) VALUES (?,?,?,?)",
            ("BBCA", "2026-07-07", "2026-07-01", 70.0),
        )
    return db


# ---------------------------------------------------------------------------
# Test 1: PIT lookup returns the row whose fetch date is <= as_of_date
# ---------------------------------------------------------------------------


def test_fundamentals_pit_returns_prior_row_for_mid_period_as_of(fundamentals_db):
    prov = StockbitFundamentalsProvider(api_client=None, db_path=fundamentals_db)
    result = prov.get_fundamentals("BBCA", as_of_date=date(2026, 6, 1))
    assert result is not None
    assert result.fetched_at is not None
    assert result.fetched_at.date() == date(2026, 5, 1)
    assert result.market_cap_idr == 500_000_000_000_000


# ---------------------------------------------------------------------------
# Test 2: PIT lookup returns None when no row exists before as_of_date
# ---------------------------------------------------------------------------


def test_fundamentals_pit_returns_none_when_no_row_before_as_of(fundamentals_db):
    prov = StockbitFundamentalsProvider(api_client=None, db_path=fundamentals_db)
    result = prov.get_fundamentals("BBCA", as_of_date=date(2026, 4, 1))
    assert result is None


# ---------------------------------------------------------------------------
# Test 3: Backfill path — PIT market cap is available and correct for as_of_date
# ---------------------------------------------------------------------------


def test_fundamentals_pit_market_cap_available_for_backfill_date(fundamentals_db):
    """Historical replay uses the PIT row, not the latest/live row."""
    prov = StockbitFundamentalsProvider(api_client=None, db_path=fundamentals_db)
    result = prov.get_fundamentals("BBCA", as_of_date=date(2026, 6, 15))
    # 2026-06-15 is between 2026-05-01 and 2026-07-01 — must return the 2026-05-01 row
    assert result is not None
    assert result.market_cap_idr == 500_000_000_000_000


# ---------------------------------------------------------------------------
# Test 4: Regression — latest/future snapshot is NOT used for an earlier as_of_date
# ---------------------------------------------------------------------------


def test_fundamentals_pit_does_not_use_future_snapshot(fundamentals_db):
    """The 2026-07-01 row must not be returned when as_of_date=2026-06-30."""
    prov = StockbitFundamentalsProvider(api_client=None, db_path=fundamentals_db)
    result_before = prov.get_fundamentals("BBCA", as_of_date=date(2026, 6, 30))
    # Must use the 2026-05-01 row, not the 2026-07-01 row
    assert result_before is not None
    assert result_before.fetched_at is not None
    assert result_before.fetched_at.date() == date(2026, 5, 1)
    assert result_before.market_cap_idr == 500_000_000_000_000

    result_after = prov.get_fundamentals("BBCA", as_of_date=date(2026, 7, 1))
    assert result_after is not None
    assert result_after.market_cap_idr == 1_000_000_000_000_000


# ---------------------------------------------------------------------------
# Shareholding PIT tests
# ---------------------------------------------------------------------------


def test_shareholding_pit_uses_report_date_as_boundary(shareholding_db):
    """report_date is the IDX filing date — use it as PIT boundary, not fetched_date."""
    prov = StockbitShareholdingProvider(api_client=None, db_path=shareholding_db)
    result = prov.get_composition("BBCA", as_of_date=date(2026, 6, 1))
    assert result is not None
    # report_date=2026-05-01 <= 2026-06-01; report_date=2026-07-01 > 2026-06-01 → excluded
    assert result.institution_pct == 65.0


def test_shareholding_pit_returns_none_before_first_report(shareholding_db):
    prov = StockbitShareholdingProvider(api_client=None, db_path=shareholding_db)
    result = prov.get_composition("BBCA", as_of_date=date(2026, 4, 30))
    assert result is None


# ---------------------------------------------------------------------------
# Application-level chain test: PIT market_cap_idr → tp_market_cap_bucket
#
# Proves that signal-backfill-observations replay calling
#   fundamentals_provider.get_fundamentals(ticker, as_of_date=historical_date)
# returns the PIT row, and the market_cap_idr produces a non-UNKNOWN bucket
# when fed through TickerProfileClassifier — the same chain the accumulation
# screen use case follows.
# ---------------------------------------------------------------------------


def _make_classifier():
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
        TickerProfileConfig,
    )

    config = TickerProfileConfig.from_mapping({})  # uses all defaults (large=10T IDR)
    return TickerProfileClassifier(config=config)


def test_pit_market_cap_feeds_through_to_non_unknown_bucket(tmp_path):
    """PIT fundamentals row → market_cap_idr → TickerProfileClassifier → 'large' bucket.

    This is the chain that signal-backfill-observations replay follows when
    a PIT snapshot exists for the observation as_of_date.
    """
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)
    with sqlite3.connect(str(db)) as conn:
        # 15T IDR — above the 10T large-cap threshold
        conn.execute(
            "INSERT OR REPLACE INTO company_fundamentals "
            "(ticker, fetched_date, market_cap_idr) VALUES (?,?,?)",
            ("BBCA", "2026-05-01", 15_000_000_000_000),
        )

    classifier = _make_classifier()

    # Simulate backfill replay at as_of_date=2026-06-01 (between snapshot and future)
    result = prov.get_fundamentals("BBCA", as_of_date=date(2026, 6, 1))
    assert result is not None, "PIT snapshot must be available for as_of_date in range"
    bucket = classifier._market_cap_bucket(result.market_cap_idr)
    assert bucket == "large", f"Expected 'large', got '{bucket}'"


def test_pit_returns_unknown_when_no_snapshot_before_as_of_date(tmp_path):
    """Regression: when no PIT row exists before as_of_date, market_cap_idr is None
    and tp_market_cap_bucket resolves to UNKNOWN — NOT to a future snapshot's value.
    """
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)
    with sqlite3.connect(str(db)) as conn:
        # Snapshot only exists from 2026-05-01 onwards
        conn.execute(
            "INSERT OR REPLACE INTO company_fundamentals "
            "(ticker, fetched_date, market_cap_idr) VALUES (?,?,?)",
            ("BBCA", "2026-05-01", 15_000_000_000_000),
        )

    classifier = _make_classifier()

    # Backfill replay for a date BEFORE the first snapshot
    result = prov.get_fundamentals("BBCA", as_of_date=date(2026, 4, 30))
    assert result is None, "No PIT data before 2026-05-01 — must return None"
    # Simulate what the screen use case does when fundamentals returns None
    bucket = classifier._market_cap_bucket(None)
    assert bucket == "UNKNOWN", f"Expected 'UNKNOWN' when market_cap_idr is None, got '{bucket}'"
