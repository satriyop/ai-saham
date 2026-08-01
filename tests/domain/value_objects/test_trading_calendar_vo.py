"""Tests for the pure Mon-Fri calendar fallback."""

from datetime import date

from src.domain.value_objects.trading_calendar import last_weekday


def test_last_weekday_returns_same_day_for_weekday():
    monday = date(2026, 6, 15)
    assert last_weekday(monday) == monday


def test_last_weekday_rolls_saturday_back_to_friday():
    saturday = date(2026, 6, 20)
    assert last_weekday(saturday) == date(2026, 6, 19)


def test_last_weekday_rolls_sunday_back_to_friday():
    sunday = date(2026, 6, 21)
    assert last_weekday(sunday) == date(2026, 6, 19)
