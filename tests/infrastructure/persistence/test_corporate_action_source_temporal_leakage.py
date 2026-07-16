"""
DQ-002G — planted future-row temporal leakage tests: corporate action calendar.

Real gap found and fixed during this task: `SQLiteCorporateActionCalendarRepository`
had no way to exclude events/date-rows that were synced (`fetched_at`) after a
decision timestamp — `get_events_for_ticker`/`get_events_for_universe`/
`get_events_by_date_role` only windowed on `event_date`, which is the
calendar date of the corporate action itself (legitimately knowable ahead of
time), not when we learned about it. A historical replay could therefore see
a corporate-action row that had not actually been synced yet as of that
decision point.

Fix: added an optional `as_of_fetched_at` parameter (default `None`,
preserving all existing callers unchanged) to all three query methods on the
port and the SQLite implementation, filtering `fetched_at <= as_of_fetched_at`
when supplied.

Layer: Infrastructure (tests only) / Application (AssessSourceAvailabilityUseCase)
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)

DECISION_DATE = date(2026, 7, 16)
DECISION_FETCHED_AT = "2026-07-16T16:00:00"
FUTURE_FETCHED_AT = "2026-07-17T09:00:00"


def _calendar() -> KnownTradingSessionCalendar:
    """DQ-002I: corporate_action_events/corporate_action_event_dates are
    FETCH_TIMESTAMP sources, so the calendar is structurally required but
    never actually queried here."""
    return KnownTradingSessionCalendar(
        sessions=(), coverage_start=date(2026, 1, 1), coverage_end=date(2026, 12, 31)
    )


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteCorporateActionCalendarRepository:
    return SQLiteCorporateActionCalendarRepository(tmp_path / "calendar.db")


def _event(
    *, source_event_id: str, fetched_at: str, event_date: date
) -> CorporateActionCalendarEvent:
    return CorporateActionCalendarEvent(
        event_type=CorporateActionType.DIVIDEND,
        source_event_id=source_event_id,
        ticker="BBCA",
        dates=(CorporateActionCalendarDate(date_role=CorporateActionDateRole.EX_DATE, event_date=event_date),),
        active=True,
        raw_payload_json="{}",
        fetched_at=fetched_at,
    )


def _decision_session() -> EffectiveMarketSession:
    decision_at = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=DECISION_DATE,
        analysis_as_of=DECISION_DATE,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


class TestCorporateActionEventsTemporalLeakage:
    def test_unbounded_read_leaks_events_synced_after_decision_time(self, repo):
        """Demonstrates the gap: an event synced after decision time, with an
        event_date inside the query window, is returned by an unbounded call —
        proving `as_of_fetched_at` is necessary, not redundant."""
        repo.save_events(
            [_event(source_event_id="future-sync", fetched_at=FUTURE_FETCHED_AT, event_date=date(2026, 7, 20))]
        )

        unbounded = repo.get_events_for_ticker("BBCA", date(2026, 7, 1), date(2026, 7, 31))

        assert len(unbounded) == 1  # the gap, absent the fix below

    def test_corporate_action_events_reader_excludes_rows_synced_after_decision_time(self, repo):
        """A corporate action event synced after decision_at must not appear
        once as_of_fetched_at is applied, even though its event_date sits
        inside the query window (event_date can legitimately be in the
        future; fetched_at — when we learned about it — cannot)."""
        repo.save_events(
            [
                _event(source_event_id="known", fetched_at=DECISION_FETCHED_AT, event_date=date(2026, 7, 20)),
                _event(source_event_id="future-sync", fetched_at=FUTURE_FETCHED_AT, event_date=date(2026, 7, 20)),
            ]
        )

        bounded = repo.get_events_for_ticker(
            "BBCA", date(2026, 7, 1), date(2026, 7, 31), as_of_fetched_at=DECISION_FETCHED_AT
        )

        assert [e.source_event_id for e in bounded] == ["known"]

    def test_get_events_by_date_role_also_respects_as_of_fetched_at(self, repo):
        repo.save_events(
            [
                _event(source_event_id="known", fetched_at=DECISION_FETCHED_AT, event_date=date(2026, 7, 20)),
                _event(source_event_id="future-sync", fetched_at=FUTURE_FETCHED_AT, event_date=date(2026, 7, 20)),
            ]
        )

        bounded = repo.get_events_by_date_role(
            date(2026, 7, 1),
            date(2026, 7, 31),
            (CorporateActionDateRole.EX_DATE,),
            as_of_fetched_at=DECISION_FETCHED_AT,
        )

        assert [e.source_event_id for e in bounded] == ["known"]

    def test_corporate_action_events_future_fetched_at_is_invalid(self, repo):
        repo.save_events(
            [_event(source_event_id="future-sync", fetched_at=FUTURE_FETCHED_AT, event_date=date(2026, 7, 20))]
        )
        unbounded = repo.get_events_for_ticker("BBCA", date(2026, 7, 1), date(2026, 7, 31))
        assert len(unbounded) == 1

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="corporate_action_events",
            effective_session=_decision_session(),
            available_at=datetime.fromisoformat(unbounded[0].fetched_at).replace(tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False

    def test_corporate_action_events_known_before_decision_is_current(self, repo):
        repo.save_events(
            [_event(source_event_id="known", fetched_at=DECISION_FETCHED_AT, event_date=date(2026, 7, 20))]
        )
        bounded = repo.get_events_for_ticker(
            "BBCA", date(2026, 7, 1), date(2026, 7, 31), as_of_fetched_at=DECISION_FETCHED_AT
        )
        assert len(bounded) == 1

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="corporate_action_events",
            effective_session=_decision_session(),
            available_at=datetime.fromisoformat(bounded[0].fetched_at).replace(tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.is_authoritative is True


class TestCorporateActionEventDatesTemporalLeakage:
    def test_corporate_action_event_dates_future_fetched_at_is_invalid(self, repo):
        repo.save_events(
            [_event(source_event_id="future-sync", fetched_at=FUTURE_FETCHED_AT, event_date=date(2026, 7, 20))]
        )
        rows = repo.get_events_by_date_role(
            date(2026, 7, 1), date(2026, 7, 31), (CorporateActionDateRole.EX_DATE,)
        )
        assert len(rows) == 1

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="corporate_action_event_dates",
            effective_session=_decision_session(),
            available_at=datetime.fromisoformat(rows[0].fetched_at).replace(tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False
