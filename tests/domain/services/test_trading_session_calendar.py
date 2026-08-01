"""Tests for KnownTradingSessionCalendar — DQ-002I pure trading-session distance."""

from datetime import date

import pytest

from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

# 2026-07-16 (Thu), 17 (Fri), 20 (Mon) are real IDX weekdays.
# 2026-07-13 (Mon), 14 (Tue), 15 (Wed), 16 (Thu), 17 (Fri) form one Mon-Fri week.
COVERAGE_START = date(2026, 7, 1)
COVERAGE_END = date(2026, 7, 31)

FRIDAY = date(2026, 7, 17)
MONDAY = date(2026, 7, 20)
TUESDAY = date(2026, 7, 21)
THURSDAY = date(2026, 7, 16)
WEDNESDAY_NEXT_WEEK = date(2026, 7, 22)


def _calendar(sessions: tuple[date, ...]) -> KnownTradingSessionCalendar:
    return KnownTradingSessionCalendar(
        sessions=sessions, coverage_start=COVERAGE_START, coverage_end=COVERAGE_END
    )


def test_same_proven_session_returns_zero():
    calendar = _calendar((FRIDAY,))
    assert calendar.sessions_apart(FRIDAY, FRIDAY) == 0


def test_friday_to_monday_returns_one_when_both_are_proven_sessions():
    calendar = _calendar((FRIDAY, MONDAY))
    assert calendar.sessions_apart(FRIDAY, MONDAY) == 1


def test_friday_to_tuesday_with_monday_absent_as_holiday_returns_one():
    """Monday is deliberately NOT in the session set (IDX holiday) — the
    proven session count must still be 1 (Tuesday only), not 2."""
    calendar = _calendar((FRIDAY, TUESDAY))
    assert calendar.sessions_apart(FRIDAY, TUESDAY) == 1


def test_multi_day_holiday_closure_counts_only_actual_supplied_sessions():
    """Thursday -> next Wednesday spans a week; only Friday and the
    following Wednesday are supplied as real sessions (a multi-day holiday
    closure removed Mon/Tue/the intervening days from the proven set)."""
    calendar = _calendar((THURSDAY, FRIDAY, WEDNESDAY_NEXT_WEEK))
    assert calendar.sessions_apart(THURSDAY, WEDNESDAY_NEXT_WEEK) == 2


def test_weekend_date_supplied_as_session_is_rejected():
    saturday = date(2026, 7, 18)
    with pytest.raises(ValueError):
        KnownTradingSessionCalendar(
            sessions=(saturday,), coverage_start=COVERAGE_START, coverage_end=COVERAGE_END
        )


def test_duplicate_session_dates_are_rejected():
    with pytest.raises(ValueError):
        KnownTradingSessionCalendar(
            sessions=(FRIDAY, FRIDAY), coverage_start=COVERAGE_START, coverage_end=COVERAGE_END
        )


def test_unsorted_session_dates_are_rejected():
    with pytest.raises(ValueError):
        KnownTradingSessionCalendar(
            sessions=(MONDAY, FRIDAY), coverage_start=COVERAGE_START, coverage_end=COVERAGE_END
        )


def test_interval_before_coverage_start_returns_none():
    calendar = KnownTradingSessionCalendar(
        sessions=(), coverage_start=date(2026, 7, 10), coverage_end=COVERAGE_END
    )
    assert calendar.sessions_apart(date(2026, 7, 1), date(2026, 7, 15)) is None


def test_interval_after_coverage_end_returns_none():
    calendar = KnownTradingSessionCalendar(
        sessions=(), coverage_start=COVERAGE_START, coverage_end=date(2026, 7, 20)
    )
    assert calendar.sessions_apart(date(2026, 7, 15), date(2026, 7, 25)) is None


def test_empty_unproven_coverage_cannot_return_zero_for_same_date_outside_coverage():
    calendar = KnownTradingSessionCalendar(
        sessions=(), coverage_start=date(2026, 8, 1), coverage_end=date(2026, 8, 31)
    )
    assert calendar.sessions_apart(FRIDAY, FRIDAY) is None


def test_session_after_coverage_end_is_rejected_at_construction():
    with pytest.raises(ValueError):
        KnownTradingSessionCalendar(
            sessions=(date(2026, 8, 1),), coverage_start=COVERAGE_START, coverage_end=COVERAGE_END
        )


def test_session_before_coverage_start_is_rejected_at_construction():
    with pytest.raises(ValueError):
        KnownTradingSessionCalendar(
            sessions=(date(2026, 6, 30),), coverage_start=COVERAGE_START, coverage_end=COVERAGE_END
        )


def test_coverage_start_after_coverage_end_is_rejected():
    with pytest.raises(ValueError):
        KnownTradingSessionCalendar(
            sessions=(), coverage_start=date(2026, 7, 31), coverage_end=date(2026, 7, 1)
        )


def test_earlier_after_later_returns_none_defensively():
    calendar = _calendar((FRIDAY, MONDAY))
    assert calendar.sessions_apart(MONDAY, FRIDAY) is None


def test_first_n_sessions_after_skips_holiday_and_fails_closed():
    """First N sessions after a signal omit holidays; insufficient coverage → None."""
    # Friday, then Tuesday (Monday holiday omitted), Wednesday.
    calendar = _calendar((FRIDAY, TUESDAY, WEDNESDAY_NEXT_WEEK))
    assert calendar.first_n_sessions_after(FRIDAY, 2) == (TUESDAY, WEDNESDAY_NEXT_WEEK)
    assert calendar.first_n_sessions_after(FRIDAY, 1) == (TUESDAY,)
    # Only two sessions after Friday — asking for 3 fails closed.
    assert calendar.first_n_sessions_after(FRIDAY, 3) is None
    # earlier outside coverage fails closed.
    assert calendar.first_n_sessions_after(date(2026, 6, 1), 1) is None
    with pytest.raises(ValueError):
        calendar.first_n_sessions_after(FRIDAY, 0)


class TestUnprovenEndpointsCannotProduceACount:
    """Both endpoints must themselves be proven sessions, not merely inside
    the coverage window — a date with no corresponding session is not
    provably a trading day (it could be a real non-session day, or a date
    the calendar simply never observed), so it must never be silently
    treated as "0 sessions" or count toward the total."""

    def test_same_date_non_session_returns_none(self):
        """MONDAY is within coverage but absent from the proven session set
        (only Friday and Tuesday are proven). Comparing MONDAY to itself
        must not return 0 (which would become CURRENT/authoritative)."""
        calendar = _calendar((FRIDAY, TUESDAY))
        assert calendar.sessions_apart(MONDAY, MONDAY) is None

    def test_non_session_earlier_endpoint_returns_none(self):
        calendar = _calendar((FRIDAY, TUESDAY))
        assert calendar.sessions_apart(MONDAY, TUESDAY) is None

    def test_non_session_later_endpoint_returns_none(self):
        calendar = _calendar((FRIDAY, TUESDAY))
        assert calendar.sessions_apart(FRIDAY, MONDAY) is None

    def test_both_proven_endpoints_still_produce_a_count(self):
        """Regression guard: the membership requirement must not break the
        ordinary proven-endpoints case."""
        calendar = _calendar((FRIDAY, TUESDAY))
        assert calendar.sessions_apart(FRIDAY, TUESDAY) == 1
