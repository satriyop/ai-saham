"""
Query-method tests for SQLiteCorporateActionCalendarRepository:
get_events_for_ticker, get_events_for_universe, get_events_by_date_role.

Save/replace/sync-marker tests live in
test_sqlite_corporate_action_calendar_repository.py.
"""

from datetime import date
from pathlib import Path

import pytest

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteCorporateActionCalendarRepository:
    return SQLiteCorporateActionCalendarRepository(tmp_path / "calendar.db")


def _event(
    *,
    event_type: CorporateActionType = CorporateActionType.DIVIDEND,
    source_event_id: str = "ev1",
    ticker: str = "BBCA",
    dates: tuple[CorporateActionCalendarDate, ...] = (),
) -> CorporateActionCalendarEvent:
    return CorporateActionCalendarEvent(
        event_type=event_type,
        source_event_id=source_event_id,
        ticker=ticker,
        dates=dates,
        raw_payload_json="{}",
        fetched_at="2026-07-11T00:00:00",
    )


def _date_row(role: CorporateActionDateRole, d: date) -> CorporateActionCalendarDate:
    return CorporateActionCalendarDate(date_role=role, event_date=d)


class TestGetEventsForTicker:
    def test_date_on_from_boundary_is_included(self, repo):
        ev = _event(dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 10)),))
        repo.save_events([ev])
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 10), date(2026, 7, 20))
        assert len(results) == 1

    def test_date_on_to_boundary_is_included(self, repo):
        ev = _event(dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 20)),))
        repo.save_events([ev])
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 10), date(2026, 7, 20))
        assert len(results) == 1

    def test_date_one_day_outside_from_is_excluded(self, repo):
        ev = _event(dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 9)),))
        repo.save_events([ev])
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 10), date(2026, 7, 20))
        assert results == []

    def test_date_one_day_outside_to_is_excluded(self, repo):
        ev = _event(dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 21)),))
        repo.save_events([ev])
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 10), date(2026, 7, 20))
        assert results == []

    def test_event_with_dates_inside_and_outside_window_returns_full_event(self, repo):
        """Regression case: matching on ONE date row must still return ALL of
        that event's date rows, not just the matching one."""
        dates = (
            _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 1, 1)),  # outside
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),  # inside
            _date_row(CorporateActionDateRole.PAYMENT_DATE, date(2026, 12, 31)),  # outside
        )
        ev = _event(dates=dates)
        repo.save_events([ev])
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 1), date(2026, 7, 31))
        assert len(results) == 1
        assert len(results[0].dates) == 3

    def test_ticker_query_is_case_insensitive(self, repo):
        ev = _event(dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),))
        repo.save_events([ev])  # stored as BBCA (uppercased by VO)
        results = repo.get_events_for_ticker("bbca", date(2026, 7, 1), date(2026, 7, 31))
        assert len(results) == 1

    def test_event_types_none_means_no_filter(self, repo):
        repo.save_events(
            [
                _event(
                    event_type=CorporateActionType.DIVIDEND,
                    source_event_id="d1",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),),
                ),
                _event(
                    event_type=CorporateActionType.IPO,
                    source_event_id="i1",
                    dates=(_date_row(CorporateActionDateRole.LISTING_DATE, date(2026, 7, 16)),),
                ),
            ]
        )
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 1), date(2026, 7, 31))
        assert len(results) == 2

    def test_event_types_filters_to_specific_tuple(self, repo):
        repo.save_events(
            [
                _event(
                    event_type=CorporateActionType.DIVIDEND,
                    source_event_id="d1",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),),
                ),
                _event(
                    event_type=CorporateActionType.IPO,
                    source_event_id="i1",
                    dates=(_date_row(CorporateActionDateRole.LISTING_DATE, date(2026, 7, 16)),),
                ),
            ]
        )
        results = repo.get_events_for_ticker(
            "BBCA", date(2026, 7, 1), date(2026, 7, 31), event_types=(CorporateActionType.DIVIDEND,)
        )
        assert len(results) == 1
        assert results[0].event_type == CorporateActionType.DIVIDEND

    def test_multiple_events_grouped_correctly_not_flattened(self, repo):
        repo.save_events(
            [
                _event(
                    source_event_id="d1",
                    dates=(
                        _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 7, 10)),
                        _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 11)),
                    ),
                ),
                _event(
                    source_event_id="d2",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 12)),),
                ),
            ]
        )
        results = repo.get_events_for_ticker("BBCA", date(2026, 7, 1), date(2026, 7, 31))
        assert len(results) == 2
        by_id = {r.source_event_id: r for r in results}
        assert len(by_id["d1"].dates) == 2
        assert len(by_id["d2"].dates) == 1


class TestGetEventsForUniverse:
    def test_empty_tickers_returns_empty_immediately(self, repo):
        assert repo.get_events_for_universe((), date(2026, 1, 1), date(2026, 12, 31)) == []

    def test_returns_events_for_multiple_tickers(self, repo):
        repo.save_events(
            [
                _event(
                    ticker="BBCA",
                    source_event_id="d1",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),),
                ),
                _event(
                    ticker="BBRI",
                    source_event_id="d2",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 16)),),
                ),
                _event(
                    ticker="BMRI",
                    source_event_id="d3",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 17)),),
                ),
            ]
        )
        results = repo.get_events_for_universe(
            ("BBCA", "BBRI"), date(2026, 7, 1), date(2026, 7, 31)
        )
        tickers = {r.ticker for r in results}
        assert tickers == {"BBCA", "BBRI"}

    def test_event_with_dates_inside_and_outside_window_returns_full_event(self, repo):
        dates = (
            _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 1, 1)),
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),
        )
        repo.save_events([_event(ticker="BBCA", dates=dates)])
        results = repo.get_events_for_universe(("BBCA",), date(2026, 7, 1), date(2026, 7, 31))
        assert len(results[0].dates) == 2

    def test_ticker_case_insensitivity(self, repo):
        repo.save_events(
            [
                _event(
                    ticker="BBCA",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),),
                )
            ]
        )
        results = repo.get_events_for_universe(("bbca",), date(2026, 7, 1), date(2026, 7, 31))
        assert len(results) == 1


class TestGetEventsByDateRole:
    def test_empty_date_roles_returns_empty_immediately(self, repo):
        assert repo.get_events_by_date_role(date(2026, 1, 1), date(2026, 12, 31), ()) == []

    def test_date_on_boundary_included(self, repo):
        repo.save_events(
            [_event(dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 10)),))]
        )
        results = repo.get_events_by_date_role(
            date(2026, 7, 10), date(2026, 7, 20), (CorporateActionDateRole.EX_DATE,)
        )
        assert len(results) == 1

    def test_role_matches_but_date_outside_window_excludes_event_even_if_other_role_inside(
        self, repo
    ):
        """Contrast with ticker/universe query semantics: here matching is on
        (role, date) pair, not just any date row of the event. An event whose
        EX_DATE is outside the window but whose CUM_DATE is inside must NOT
        match a query filtered to date_roles=(EX_DATE,)."""
        dates = (
            _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 7, 15)),  # inside window
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 1, 1)),  # outside window
        )
        repo.save_events([_event(dates=dates)])
        results = repo.get_events_by_date_role(
            date(2026, 7, 1), date(2026, 7, 31), (CorporateActionDateRole.EX_DATE,)
        )
        assert results == []

    def test_event_matching_via_role_returns_all_its_date_rows(self, repo):
        dates = (
            _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 1, 1)),
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),
        )
        repo.save_events([_event(dates=dates)])
        results = repo.get_events_by_date_role(
            date(2026, 7, 1), date(2026, 7, 31), (CorporateActionDateRole.EX_DATE,)
        )
        assert len(results) == 1
        assert len(results[0].dates) == 2

    def test_event_types_filter_applies(self, repo):
        repo.save_events(
            [
                _event(
                    event_type=CorporateActionType.DIVIDEND,
                    source_event_id="d1",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 15)),),
                ),
                _event(
                    event_type=CorporateActionType.RIGHTS_ISSUE,
                    source_event_id="ri1",
                    dates=(_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 16)),),
                ),
            ]
        )
        results = repo.get_events_by_date_role(
            date(2026, 7, 1),
            date(2026, 7, 31),
            (CorporateActionDateRole.EX_DATE,),
            event_types=(CorporateActionType.DIVIDEND,),
        )
        assert len(results) == 1
        assert results[0].event_type == CorporateActionType.DIVIDEND

    def test_multiple_roles_in_filter(self, repo):
        repo.save_events(
            [
                _event(
                    source_event_id="d1",
                    dates=(_date_row(CorporateActionDateRole.CUM_DATE, date(2026, 7, 15)),),
                ),
                _event(
                    source_event_id="d2",
                    dates=(_date_row(CorporateActionDateRole.PAYMENT_DATE, date(2026, 7, 16)),),
                ),
            ]
        )
        results = repo.get_events_by_date_role(
            date(2026, 7, 1),
            date(2026, 7, 31),
            (CorporateActionDateRole.CUM_DATE, CorporateActionDateRole.PAYMENT_DATE),
        )
        assert len(results) == 2
