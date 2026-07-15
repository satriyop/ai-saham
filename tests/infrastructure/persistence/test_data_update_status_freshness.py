"""Pure function tests for data update status freshness classification.

Layer: Test
"""

from datetime import date

from src.infrastructure.persistence.data_update_status_freshness import (
    freshness_status,
    parse_dateish,
    range_label,
)


def test_range_label_empty_single_and_range():
    assert range_label(None, None) == "-"
    assert range_label("2026-07-15", "2026-07-15") == "2026-07-15"
    assert range_label("2026-07-01T01:00:00", "2026-07-15T01:00:00") == "2026-07-01..2026-07-15"


def test_parse_dateish_none_invalid_month_iso_and_datetime():
    assert parse_dateish(None, "range") is None
    assert parse_dateish("not-a-date", "range") is None
    assert parse_dateish("2026-07", "month") == date(2026, 7, 1)
    assert parse_dateish("2026-07-15", "range") == date(2026, 7, 15)
    assert parse_dateish("2026-07-15T10:30:00", "range") == date(2026, 7, 15)


def test_freshness_empty_returns_empty_issue():
    status, impact, issue = freshness_status(
        table="candles",
        freshness="range",
        rows=0,
        ticker_count=0,
        requested_tickers=5,
        max_raw=None,
        expected_trading_day=None,
        today=date(2026, 7, 15),
    )
    assert status == "empty"
    assert impact == "No rows for requested tickers."
    assert issue == "candles has no rows for requested tickers"


def test_range_ready_partial_stale_and_pending_eod():
    today = date(2026, 7, 15)
    expected = date(2026, 7, 15)

    # ready
    status, impact, issue = freshness_status(
        table="candles",
        freshness="range",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-15",
        expected_trading_day=expected,
        today=today,
    )
    assert status == "ready"
    assert impact == "Current through today."
    assert issue is None

    # partial
    status, impact, issue = freshness_status(
        table="candles",
        freshness="range",
        rows=80,
        ticker_count=3,
        requested_tickers=5,
        max_raw="2026-07-15",
        expected_trading_day=expected,
        today=today,
    )
    assert status == "partial"
    assert impact == "Some requested tickers are missing."
    assert issue == "candles has 3/5 requested tickers"

    # stale (market closed)
    status, impact, issue = freshness_status(
        table="candles",
        freshness="range",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-10",
        expected_trading_day=expected,
        today=today,
    )
    assert status == "stale"
    assert impact == "Latest stored date is before expected trading day 2026-07-15."
    assert issue == "candles is stale"

    # pending-eod (market open, within 3 days)
    status, impact, issue = freshness_status(
        table="candles",
        freshness="range",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-14",
        expected_trading_day=expected,
        today=today,
        market_is_open=True,
    )
    assert status == "pending-eod"
    assert impact == "EOD not yet available. Re-fetch after close."
    assert issue is None


def test_today_freshness_ready_partial_and_stale():
    today = date(2026, 7, 15)

    # ready
    status, impact, issue = freshness_status(
        table="analyst_cache",
        freshness="today",
        rows=5,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-15",
        expected_trading_day=None,
        today=today,
    )
    assert status == "ready"
    assert impact == "Fetched today."
    assert issue is None

    # partial (same date, missing tickers)
    status, impact, issue = freshness_status(
        table="analyst_cache",
        freshness="today",
        rows=3,
        ticker_count=3,
        requested_tickers=5,
        max_raw="2026-07-15",
        expected_trading_day=None,
        today=today,
    )
    assert status == "partial"
    assert impact == "Some requested tickers are missing."
    assert issue == "analyst_cache has 3/5 requested tickers"

    # stale
    status, impact, issue = freshness_status(
        table="analyst_cache",
        freshness="today",
        rows=5,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-14",
        expected_trading_day=None,
        today=today,
    )
    assert status == "stale"
    assert impact == "Latest fetched date is not today (2026-07-15)."
    assert issue == "analyst_cache cache is stale"


def test_month_freshness_ready_partial_and_stale():
    today = date(2026, 7, 15)

    # ready
    status, impact, issue = freshness_status(
        table="seasonality_cache",
        freshness="month",
        rows=12,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07",
        expected_trading_day=None,
        today=today,
    )
    assert status == "ready"
    assert impact == "Fetched for current month."
    assert issue is None

    # partial (current month, missing tickers)
    status, impact, issue = freshness_status(
        table="seasonality_cache",
        freshness="month",
        rows=8,
        ticker_count=3,
        requested_tickers=5,
        max_raw="2026-07",
        expected_trading_day=None,
        today=today,
    )
    assert status == "partial"
    assert impact == "Some requested tickers are missing."
    assert issue == "seasonality_cache has 3/5 requested tickers"

    # stale (wrong month)
    status, impact, issue = freshness_status(
        table="seasonality_cache",
        freshness="month",
        rows=12,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-06",
        expected_trading_day=None,
        today=today,
    )
    assert status == "stale"
    assert impact == "Latest fetched month is not current month (2026-07)."
    assert issue == "seasonality_cache cache is stale"


def test_ttl30_and_ttl7_ready_partial_and_stale():
    today = date(2026, 7, 15)

    # ttl30: 30 days old → ready
    status, impact, issue = freshness_status(
        table="stock_meta",
        freshness="ttl30",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-06-15",
        expected_trading_day=None,
        today=today,
    )
    assert status == "ready"
    assert impact == "Fresh within 30d TTL."
    assert issue is None

    # ttl30: 31 days old → stale
    status, impact, issue = freshness_status(
        table="stock_meta",
        freshness="ttl30",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-06-14",
        expected_trading_day=None,
        today=today,
    )
    assert status == "stale"
    assert impact == "Latest cache is older than 30d TTL."
    assert issue == "stock_meta cache is stale"

    # ttl7: 7 days old → ready
    status, impact, issue = freshness_status(
        table="shareholding_composition",
        freshness="ttl7",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-08",
        expected_trading_day=None,
        today=today,
    )
    assert status == "ready"
    assert impact == "Fresh within 7d TTL."
    assert issue is None

    # ttl7: 8 days old → stale
    status, impact, issue = freshness_status(
        table="shareholding_composition",
        freshness="ttl7",
        rows=100,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-07",
        expected_trading_day=None,
        today=today,
    )
    assert status == "stale"
    assert impact == "Latest cache is older than 7d TTL."
    assert issue == "shareholding_composition cache is stale"

    # ttl7: partial within TTL → partial
    status, impact, issue = freshness_status(
        table="shareholding_composition",
        freshness="ttl7",
        rows=60,
        ticker_count=3,
        requested_tickers=5,
        max_raw="2026-07-08",
        expected_trading_day=None,
        today=today,
    )
    assert status == "partial"
    assert impact == "Some requested tickers are missing."
    assert issue == "shareholding_composition has 3/5 requested tickers"


def test_unknown_freshness_fallback():
    today = date(2026, 7, 15)

    # no partial → ready
    status, impact, issue = freshness_status(
        table="unknown_table",
        freshness="unknown",
        rows=50,
        ticker_count=5,
        requested_tickers=5,
        max_raw="2026-07-15",
        expected_trading_day=None,
        today=today,
    )
    assert status == "ready"
    assert impact == "Rows exist for requested tickers."
    assert issue is None

    # partial → partial
    status, impact, issue = freshness_status(
        table="unknown_table",
        freshness="unknown",
        rows=30,
        ticker_count=3,
        requested_tickers=5,
        max_raw="2026-07-15",
        expected_trading_day=None,
        today=today,
    )
    assert status == "partial"
    assert impact == "Some requested tickers are missing."
    assert issue == "unknown_table has 3/5 requested tickers"
