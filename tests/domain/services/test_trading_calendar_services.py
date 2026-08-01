"""Unit tests for pure weekday trading-calendar helpers."""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.services.trading_calendar import (
    first_weekday_session_after,
    inclusive_weekday_sessions,
    is_weekday_session,
    nth_weekday_session_on_or_after,
    trading_sessions_apart,
)


def test_inclusive_weekday_sessions_exact_horizons() -> None:
    # Signal Wed 2026-07-01 → first session Thu 2026-07-02.
    start = date(2026, 7, 2)
    assert inclusive_weekday_sessions(start, date(2026, 7, 6)) == 3  # H3
    assert inclusive_weekday_sessions(start, date(2026, 7, 15)) == 10  # H10
    assert inclusive_weekday_sessions(start, date(2026, 7, 29)) == 20  # H20


def test_inclusive_weekday_sessions_rejects_weekend_endpoints() -> None:
    assert inclusive_weekday_sessions(date(2026, 7, 2), date(2026, 7, 11)) is None  # Sat end
    assert inclusive_weekday_sessions(date(2026, 7, 4), date(2026, 7, 10)) is None  # Sat start
    assert inclusive_weekday_sessions(date(2026, 7, 15), date(2026, 7, 2)) is None  # inverted


def test_overlong_span_is_not_ten_sessions() -> None:
    count = inclusive_weekday_sessions(date(2026, 7, 20), date(2026, 12, 31))
    assert count is not None
    assert count > 10


def test_nth_and_first_session_helpers() -> None:
    assert first_weekday_session_after(date(2026, 7, 1)) == date(2026, 7, 2)
    assert first_weekday_session_after(date(2026, 7, 3)) == date(2026, 7, 6)  # Fri → Mon
    assert nth_weekday_session_on_or_after(date(2026, 7, 2), 10) == date(2026, 7, 15)
    assert nth_weekday_session_on_or_after(date(2026, 7, 4), 1) == date(2026, 7, 6)  # Sat → Mon
    with pytest.raises(ValueError):
        nth_weekday_session_on_or_after(date(2026, 7, 2), 0)


def test_is_weekday_session_and_sessions_apart() -> None:
    assert is_weekday_session(date(2026, 7, 2)) is True
    assert is_weekday_session(date(2026, 7, 4)) is False
    assert trading_sessions_apart(date(2026, 7, 2), date(2026, 7, 15)) == 9
