"""Unit tests for gap-free availability calendar window selection."""

from datetime import date

import pytest

from src.application.services.availability_calendar_window import (
    resolve_gap_free_availability_calendar_start,
)


def test_prefers_longest_gap_free_suffix_capped_at_max_sessions():
    sessions = (
        date(2026, 7, 10),
        date(2026, 7, 13),
        date(2026, 7, 14),
        date(2026, 7, 15),
        date(2026, 7, 16),
        date(2026, 7, 17),
    )
    start = resolve_gap_free_availability_calendar_start(
        sessions=sessions,
        coverage_end=date(2026, 7, 17),
        max_sessions=5,
    )
    assert start == date(2026, 7, 13)


def test_shrinks_before_unexplained_weekday_holiday():
    sessions = (
        date(2026, 6, 12),
        date(2026, 6, 15),
        # 2026-06-16 holiday / unexplained weekday gap
        date(2026, 6, 17),
        date(2026, 6, 18),
        date(2026, 6, 19),
    )
    start = resolve_gap_free_availability_calendar_start(
        sessions=sessions,
        coverage_end=date(2026, 6, 19),
        max_sessions=5,
    )
    assert start == date(2026, 6, 17)


def test_falls_back_to_single_day_when_only_end_is_safe():
    sessions = (
        date(2026, 6, 15),
        # gap
        date(2026, 6, 17),
    )
    start = resolve_gap_free_availability_calendar_start(
        sessions=sessions,
        coverage_end=date(2026, 6, 17),
        max_sessions=5,
    )
    assert start == date(2026, 6, 17)


def test_coverage_end_missing_from_sessions_returns_end():
    start = resolve_gap_free_availability_calendar_start(
        sessions=(date(2026, 6, 15),),
        coverage_end=date(2026, 6, 17),
        max_sessions=5,
    )
    assert start == date(2026, 6, 17)


def test_max_sessions_must_be_positive():
    with pytest.raises(ValueError, match="max_sessions"):
        resolve_gap_free_availability_calendar_start(
            sessions=(date(2026, 7, 17),),
            coverage_end=date(2026, 7, 17),
            max_sessions=0,
        )
