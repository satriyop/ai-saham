"""Tests for stockbit_pit_cache shared primitives."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta

from src.infrastructure.browser.stockbit_pit_cache import (
    fetched_at_is_fresh,
    fetched_date_as_of_filter,
    has_fresh_ticker_row,
    latest_fetched_order,
    safe_cache_read,
    safe_cache_write,
    safe_schema_update,
)

# ── fetched_date_as_of_filter ──────────────────────────────────────────────────


def test_fetched_date_as_of_filter_none():
    frag, params = fetched_date_as_of_filter(None)
    assert frag == ""
    assert params == ()


def test_fetched_date_as_of_filter_with_date():
    frag, params = fetched_date_as_of_filter(date(2026, 6, 1))
    assert "date(substr(fetched_date,1,10)) <= date(?)" in frag
    assert params == ("2026-06-01",)


def test_fetched_date_as_of_filter_custom_column():
    frag, params = fetched_date_as_of_filter(date(2026, 6, 1), column="custom_date")
    assert "date(substr(custom_date,1,10))" in frag
    assert params == ("2026-06-01",)


# ── latest_fetched_order ───────────────────────────────────────────────────────


def test_latest_fetched_order_default():
    result = latest_fetched_order()
    assert "ORDER BY date(substr(fetched_date,1,10)) DESC, fetched_date DESC" == result


def test_latest_fetched_order_custom_column():
    result = latest_fetched_order(column="custom_col")
    assert "date(substr(custom_col,1,10)) DESC, custom_col DESC" in result


# ── fetched_at_is_fresh ────────────────────────────────────────────────────────


def test_fetched_at_is_fresh_none():
    assert fetched_at_is_fresh(None, ttl_days=0) is False
    assert fetched_at_is_fresh(None, ttl_days=7) is False


def test_fetched_at_is_fresh_today_ttl_zero():
    dt = datetime.now()
    assert fetched_at_is_fresh(dt, ttl_days=0) is True


def test_fetched_at_is_fresh_yesterday_ttl_zero():
    dt = datetime.now() - timedelta(days=1)
    assert fetched_at_is_fresh(dt, ttl_days=0) is False


def test_fetched_at_is_fresh_7_days_old_ttl_7():
    dt = datetime.now() - timedelta(days=7)
    assert fetched_at_is_fresh(dt, ttl_days=7) is True


def test_fetched_at_is_fresh_8_days_old_ttl_7():
    dt = datetime.now() - timedelta(days=8)
    assert fetched_at_is_fresh(dt, ttl_days=7) is False


def test_fetched_at_is_fresh_with_explicit_today():
    today = date(2026, 6, 15)
    dt = datetime(2026, 6, 10, 9)
    assert fetched_at_is_fresh(dt, ttl_days=5, today=today) is True
    assert fetched_at_is_fresh(dt, ttl_days=4, today=today) is False


# ── has_fresh_ticker_row ───────────────────────────────────────────────────────


def _make_table(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE test_cache (ticker TEXT NOT NULL, fetched_date TEXT NOT NULL)")


def _insert_row(conn: sqlite3.Connection, ticker: str, fetched_date: str) -> None:
    conn.execute(
        "INSERT INTO test_cache (ticker, fetched_date) VALUES (?, ?)",
        (ticker, fetched_date),
    )


def test_has_fresh_ticker_row_no_row():
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    assert has_fresh_ticker_row(conn, table="test_cache", ticker="BBCA", ttl_days=7) is False
    conn.close()


def test_has_fresh_ticker_row_stale():
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    old_date = (date.today() - timedelta(days=10)).isoformat()
    _insert_row(conn, "BBCA", old_date)
    assert has_fresh_ticker_row(conn, table="test_cache", ticker="BBCA", ttl_days=7) is False
    conn.close()


def test_has_fresh_ticker_row_fresh():
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    fresh_date = date.today().isoformat()
    _insert_row(conn, "BBCA", fresh_date)
    assert has_fresh_ticker_row(conn, table="test_cache", ticker="BBCA", ttl_days=7) is True
    conn.close()


# ── safe_cache_read ────────────────────────────────────────────────────────────


def test_safe_cache_read_returns_value(caplog):
    caplog.set_level(logging.DEBUG)
    result = safe_cache_read(
        logger=logging.getLogger("test"),
        label="test_label",
        ticker="BBCA",
        default="fallback",
        read=lambda: "hello",
    )
    assert result == "hello"
    assert not caplog.text


def test_safe_cache_read_returns_default_on_exception(caplog):
    caplog.set_level(logging.DEBUG)

    def failing():
        raise ValueError("boom")

    result = safe_cache_read(
        logger=logging.getLogger("test"),
        label="test_label",
        ticker="BBCA",
        default="fallback",
        read=failing,
    )
    assert result == "fallback"
    assert "test_label read failed for BBCA" in caplog.text
    assert "boom" in caplog.text


# ── safe_cache_write ───────────────────────────────────────────────────────────


def test_safe_cache_write_success():
    called = False

    def do_write():
        nonlocal called
        called = True

    safe_cache_write(
        logger=logging.getLogger("test"),
        label="test_label",
        ticker="BBCA",
        write=do_write,
    )
    assert called


def test_safe_cache_write_swallows_exception(caplog):
    caplog.set_level(logging.DEBUG)

    def failing():
        raise ValueError("boom")

    safe_cache_write(
        logger=logging.getLogger("test"),
        label="test_label",
        ticker="BBCA",
        write=failing,
    )
    assert "test_label write failed for BBCA" in caplog.text
    assert "boom" in caplog.text


# ── safe_schema_update ─────────────────────────────────────────────────────────


def test_safe_schema_update_success():
    called = False

    def do_update():
        nonlocal called
        called = True

    safe_schema_update(
        logger=logging.getLogger("test"),
        label="test_label",
        update=do_update,
    )
    assert called


def test_safe_schema_update_swallows_exception(caplog):
    caplog.set_level(logging.WARNING)

    def failing():
        raise ValueError("boom")

    safe_schema_update(
        logger=logging.getLogger("test"),
        label="test_label",
        update=failing,
    )
    assert "test_label schema error" in caplog.text
    assert "boom" in caplog.text
