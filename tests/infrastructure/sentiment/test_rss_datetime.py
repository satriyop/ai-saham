"""Host-TZ-independent RSS datetime parsing (CI TZ=UTC)."""

from __future__ import annotations

from datetime import datetime

from src.infrastructure.sentiment.rss_datetime import parse_rss_datetime


def test_parse_rss_datetime_wib_offset() -> None:
    result = parse_rss_datetime("Sun, 28 Jun 2026 10:00:00 WIB")
    assert result == datetime(2026, 6, 28, 10, 0, 0)


def test_parse_rss_datetime_numeric_offset() -> None:
    result = parse_rss_datetime("Sun, 28 Jun 2026 10:00:00 +0700")
    assert result == datetime(2026, 6, 28, 10, 0, 0)


def test_parse_rss_datetime_empty_and_invalid() -> None:
    assert parse_rss_datetime("") is None
    assert parse_rss_datetime("not a date") is None
