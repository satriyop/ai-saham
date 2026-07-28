"""Tests for SQLiteMacroCalendarRepository — upsert, markers, window query, PIT."""

from datetime import date
from pathlib import Path

import pytest

from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)
from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
    SQLiteMacroCalendarRepository,
)


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteMacroCalendarRepository:
    return SQLiteMacroCalendarRepository(tmp_path / "macro.db")


def _event(
    *,
    source_event_id: str = "e1",
    event_date: date = date(2026, 7, 10),
    category: MacroEventCategory = MacroEventCategory.OTHER,
    title: str = "Car Sales YoY",
    actual: str | None = "12.0%",
    fetched_at: str = "2026-07-11T00:00:00",
) -> MacroCalendarEvent:
    return MacroCalendarEvent(
        source_event_id=source_event_id,
        event_date=event_date,
        category=category,
        title=title,
        actual=actual,
        raw_payload_json="{}",
        fetched_at=fetched_at,
    )


def _count(repo: SQLiteMacroCalendarRepository) -> int:
    with repo._get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM macro_calendar_events").fetchone()["c"]


class TestSaveIdempotency:
    def test_save_twice_one_row(self, repo):
        repo.save_events([_event()])
        repo.save_events([_event(actual="13.0%", fetched_at="2026-07-12T00:00:00")])
        assert _count(repo) == 1
        with repo._get_connection() as conn:
            row = conn.execute(
                "SELECT actual, fetched_at FROM macro_calendar_events WHERE source_event_id=?",
                ("e1",),
            ).fetchone()
        assert row["actual"] == "13.0%"
        assert row["fetched_at"] == "2026-07-12T00:00:00"

    def test_empty_save_noop(self, repo):
        repo.save_events([])
        assert _count(repo) == 0


class TestSyncMarkers:
    def test_success_marker_counts_as_synced(self, repo):
        assert repo.has_synced_for_date(date(2026, 7, 11)) is False
        repo.mark_synced(date(2026, 7, 11), status="success")
        assert repo.has_synced_for_date(date(2026, 7, 11)) is True

    def test_partial_marker_does_not_count(self, repo):
        repo.mark_synced(date(2026, 7, 11), status="partial")
        assert repo.has_synced_for_date(date(2026, 7, 11)) is False


class TestQueries:
    def test_window_and_category_filter(self, repo):
        repo.save_events(
            [
                _event(
                    source_event_id="b1",
                    event_date=date(2026, 7, 10),
                    category=MacroEventCategory.BI_RATE,
                    title="BI Rate",
                ),
                _event(
                    source_event_id="c1",
                    event_date=date(2026, 7, 1),
                    category=MacroEventCategory.INFLATION,
                    title="CPI",
                ),
                _event(
                    source_event_id="o1",
                    event_date=date(2026, 6, 1),
                    category=MacroEventCategory.OTHER,
                    title="Other",
                ),
            ]
        )
        window = repo.get_events_in_window(date(2026, 7, 1), date(2026, 7, 31))
        assert {e.source_event_id for e in window} == {"b1", "c1"}

        bi_only = repo.get_events_in_window(
            date(2026, 1, 1),
            date(2026, 12, 31),
            categories=(MacroEventCategory.BI_RATE,),
        )
        assert [e.source_event_id for e in bi_only] == ["b1"]

    def test_as_of_fetched_at_excludes_newer(self, repo):
        repo.save_events(
            [
                _event(source_event_id="old", fetched_at="2026-07-01T00:00:00"),
                _event(source_event_id="new", fetched_at="2026-07-20T00:00:00"),
            ]
        )
        pit = repo.get_events_in_window(
            date(2026, 1, 1),
            date(2026, 12, 31),
            as_of_fetched_at="2026-07-10T00:00:00",
        )
        assert [e.source_event_id for e in pit] == ["old"]
