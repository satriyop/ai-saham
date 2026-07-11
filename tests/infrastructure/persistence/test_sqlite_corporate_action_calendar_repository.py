"""
Tests for SQLiteCorporateActionCalendarRepository — save idempotency, date-role
row replacement, and sync markers.

Query-method tests (get_events_for_ticker / get_events_for_universe /
get_events_by_date_role) live in
test_sqlite_corporate_action_calendar_repository_queries.py.
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
    active: bool = False,
    event_note: str | None = None,
) -> CorporateActionCalendarEvent:
    return CorporateActionCalendarEvent(
        event_type=event_type,
        source_event_id=source_event_id,
        ticker=ticker,
        dates=dates,
        active=active,
        event_note=event_note,
        raw_payload_json="{}",
        fetched_at="2026-07-11T00:00:00",
    )


def _date_row(role: CorporateActionDateRole, d: date) -> CorporateActionCalendarDate:
    return CorporateActionCalendarDate(date_role=role, event_date=d)


def _count_event_rows(repo: SQLiteCorporateActionCalendarRepository) -> int:
    with repo._get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM corporate_action_events").fetchone()["c"]


def _count_date_rows(
    repo: SQLiteCorporateActionCalendarRepository, source_event_id: str | None = None
) -> int:
    with repo._get_connection() as conn:
        if source_event_id is None:
            return conn.execute(
                "SELECT COUNT(*) AS c FROM corporate_action_event_dates"
            ).fetchone()["c"]
        return conn.execute(
            "SELECT COUNT(*) AS c FROM corporate_action_event_dates WHERE source_event_id=?",
            (source_event_id,),
        ).fetchone()["c"]


class TestSaveIdempotency:
    def test_save_same_event_twice_yields_exactly_one_row(self, repo):
        ev = _event()
        repo.save_events([ev])
        repo.save_events([ev])
        assert _count_event_rows(repo) == 1

    def test_second_save_with_changed_fields_updates_columns(self, repo):
        ev1 = _event(active=False, event_note=None)
        repo.save_events([ev1])
        ev2 = _event(active=True, event_note="updated note")
        repo.save_events([ev2])

        with repo._get_connection() as conn:
            row = conn.execute(
                "SELECT active, event_note FROM corporate_action_events WHERE source_event_id=?",
                ("ev1",),
            ).fetchone()
        assert row["active"] == 1
        assert row["event_note"] == "updated note"
        assert _count_event_rows(repo) == 1

    def test_save_events_empty_list_is_noop(self, repo):
        repo.save_events([])
        assert _count_event_rows(repo) == 0

    def test_resave_same_event_and_dates_keeps_original_n_rows(self, repo):
        dates = (
            _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 7, 8)),
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 9)),
        )
        ev = _event(dates=dates)
        repo.save_events([ev])
        repo.save_events([ev])
        assert _count_date_rows(repo, "ev1") == 2


class TestDateRoleRowReplacement:
    """Regression-critical: re-saving an event with a different date-role set
    must replace (not accumulate) that event's date rows, while leaving other
    events' date rows untouched."""

    def test_resave_with_different_roles_replaces_rows(self, repo):
        original_dates = (
            _date_row(CorporateActionDateRole.CUM_DATE, date(2026, 7, 1)),
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 2)),
            _date_row(CorporateActionDateRole.RECORDING_DATE, date(2026, 7, 3)),
        )
        repo.save_events([_event(dates=original_dates)])

        new_dates = (
            _date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 9)),
            _date_row(CorporateActionDateRole.PAYMENT_DATE, date(2026, 7, 20)),
        )
        repo.save_events([_event(dates=new_dates)])

        with repo._get_connection() as conn:
            rows = conn.execute(
                "SELECT date_role, event_date FROM corporate_action_event_dates WHERE source_event_id=?",
                ("ev1",),
            ).fetchall()
        roles = {r["date_role"] for r in rows}
        assert roles == {
            CorporateActionDateRole.EX_DATE.value,
            CorporateActionDateRole.PAYMENT_DATE.value,
        }
        # cum_date/recording_date gone, ex_date updated to new date
        ex_row = next(r for r in rows if r["date_role"] == CorporateActionDateRole.EX_DATE.value)
        assert ex_row["event_date"] == "2026-07-09"

    def test_different_events_date_rows_untouched_by_resave(self, repo):
        event_a_dates = (_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 1)),)
        event_b_dates = (_date_row(CorporateActionDateRole.EX_DATE, date(2026, 8, 1)),)
        repo.save_events(
            [
                _event(source_event_id="A", dates=event_a_dates),
                _event(source_event_id="B", dates=event_b_dates),
            ]
        )
        # Re-save A with a totally different role set.
        repo.save_events(
            [_event(source_event_id="A", dates=(_date_row(CorporateActionDateRole.PAYMENT_DATE, date(2026, 9, 1)),))]
        )
        assert _count_date_rows(repo, "B") == 1
        with repo._get_connection() as conn:
            b_row = conn.execute(
                "SELECT date_role, event_date FROM corporate_action_event_dates WHERE source_event_id=?",
                ("B",),
            ).fetchone()
        assert b_row["date_role"] == CorporateActionDateRole.EX_DATE.value
        assert b_row["event_date"] == "2026-08-01"

    def test_resave_with_empty_dates_deletes_all_date_rows(self, repo):
        dates = (_date_row(CorporateActionDateRole.EX_DATE, date(2026, 7, 1)),)
        repo.save_events([_event(dates=dates)])
        assert _count_date_rows(repo, "ev1") == 1

        repo.save_events([_event(dates=())])
        assert _count_date_rows(repo, "ev1") == 0
        # Event row itself remains.
        assert _count_event_rows(repo) == 1


class TestSyncMarkers:
    def test_has_synced_for_date_false_when_no_marker(self, repo):
        assert repo.has_synced_for_date(date(2026, 7, 11), (CorporateActionType.DIVIDEND,)) is False

    def test_mark_synced_success_then_has_synced_true(self, repo):
        types = (CorporateActionType.DIVIDEND,)
        repo.mark_synced(date(2026, 7, 11), types, status="success")
        assert repo.has_synced_for_date(date(2026, 7, 11), types) is True

    def test_mark_synced_partial_does_not_count_as_synced(self, repo):
        types = (CorporateActionType.DIVIDEND,)
        repo.mark_synced(date(2026, 7, 11), types, status="partial")
        assert repo.has_synced_for_date(date(2026, 7, 11), types) is False

    def test_different_event_type_subsets_have_independent_sync_keys(self, repo):
        repo.mark_synced(date(2026, 7, 11), (CorporateActionType.DIVIDEND, CorporateActionType.IPO), status="success")
        assert repo.has_synced_for_date(date(2026, 7, 11), (CorporateActionType.RUPS,)) is False

    def test_same_subset_different_order_collapses_to_same_sync_key(self, repo):
        repo.mark_synced(
            date(2026, 7, 11),
            (CorporateActionType.DIVIDEND, CorporateActionType.IPO),
            status="success",
        )
        assert (
            repo.has_synced_for_date(date(2026, 7, 11), (CorporateActionType.IPO, CorporateActionType.DIVIDEND))
            is True
        )

    def test_mark_synced_twice_upserts_status(self, repo):
        types = (CorporateActionType.DIVIDEND,)
        repo.mark_synced(date(2026, 7, 11), types, status="partial")
        repo.mark_synced(date(2026, 7, 11), types, status="success")
        assert repo.has_synced_for_date(date(2026, 7, 11), types) is True
