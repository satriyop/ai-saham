"""Unit tests for ticker dashboard freshness / empty-state helpers."""

from datetime import date, datetime

from src.adapters.cli.view_ticker_status import (
    CacheStatus,
    build_freshness_item,
    classify_optional,
    classify_sequence,
    empty_state_message,
    format_freshness_lines,
    format_freshness_mark,
)


def test_empty_state_message_missing_with_hint():
    msg = empty_state_message(
        CacheStatus.MISSING,
        hint="saham fetch market BBCA",
    )
    assert msg == "not fetched — run: saham fetch market BBCA"


def test_empty_state_message_empty_window_with_last_known():
    msg = empty_state_message(
        CacheStatus.EMPTY,
        window_label="last 12 months",
        last_known=date(2026, 3, 25),
    )
    assert msg == "none in last 12 months (last: 2026-03-25)"


def test_classify_optional_and_stale():
    today = date(2026, 7, 24)
    assert classify_optional(None) is CacheStatus.MISSING
    assert classify_optional(object(), as_of=today, today=today, ttl_days=7) is CacheStatus.OK
    assert (
        classify_optional(
            object(),
            as_of=date(2026, 7, 1),
            today=today,
            ttl_days=7,
        )
        is CacheStatus.STALE
    )


def test_classify_sequence_empty_vs_missing():
    today = date(2026, 7, 24)
    assert classify_sequence([]) is CacheStatus.MISSING
    assert classify_sequence([], ever_fetched=True) is CacheStatus.EMPTY
    assert classify_sequence([], last_known=date(2026, 3, 1)) is CacheStatus.EMPTY
    assert (
        classify_sequence(
            [1],
            as_of=datetime(2026, 7, 20, 12, 0, 0),
            today=today,
            ttl_days=2,
        )
        is CacheStatus.STALE
    )


def test_format_freshness_lines_groups_statuses():
    today = date(2026, 7, 24)
    items = [
        build_freshness_item("price", "Price", CacheStatus.OK, as_of=today, today=today),
        build_freshness_item("flow", "Flow", CacheStatus.MISSING, today=today),
        build_freshness_item(
            "fundamentals",
            "Fundamentals",
            CacheStatus.STALE,
            as_of=date(2026, 7, 1),
            today=today,
        ),
        build_freshness_item(
            "insider",
            "Insider",
            CacheStatus.EMPTY,
            as_of=date(2026, 3, 25),
            today=today,
        ),
    ]
    lines = format_freshness_lines("BBCA", items, as_of=today)
    assert lines[0] == "BBCA · as of 2026-07-24"
    assert "Price ✓" in lines[1]
    assert "Flow ✗" in lines[1]
    assert "Missing: Flow" in lines
    assert "Empty: Insider" in lines
    assert "Stale: Fundamentals (23d)" in lines
    assert format_freshness_mark(CacheStatus.OK) == "✓"
