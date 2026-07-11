"""
Tests for SyncCorporateActionCalendarUseCase — cache-aware market-wide
corporate action calendar sync workflow.

Uses in-memory FakeProvider/FakeRepository (with call tracking) for most
tests, per the FakeProvider/FakeRepository convention in
test_fetch_broker_daily_flows.py. The self-healing round-trip test uses the
REAL SQLite repository (per test_import_broker_data.py's tmp_path convention)
since it verifies the has_synced_for_date/mark_synced contract end-to-end.
"""

from datetime import date
from pathlib import Path

import pytest

from src.application.ports.corporate_action_calendar_provider import (
    CorporateActionCalendarFetchError,
)
from src.application.use_case.sync_corporate_action_calendar_use_case import (
    SyncCorporateActionCalendarRequest,
    SyncCorporateActionCalendarUseCase,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)

_DIVIDEND_IPO = (CorporateActionType.DIVIDEND, CorporateActionType.IPO)
_TODAY = date(2026, 7, 11)


def _event(
    event_type: CorporateActionType = CorporateActionType.DIVIDEND,
    source_event_id: str = "ev1",
    ticker: str = "BBCA",
) -> CorporateActionCalendarEvent:
    return CorporateActionCalendarEvent(
        event_type=event_type,
        source_event_id=source_event_id,
        ticker=ticker,
        dates=(CorporateActionCalendarDate(date_role=CorporateActionDateRole.EX_DATE, event_date=_TODAY),),
        raw_payload_json="{}",
        fetched_at=_TODAY.isoformat(),
    )


class FakeProvider:
    """Returns a scripted result or raises a scripted exception; tracks calls."""

    def __init__(self, result=None, exception: Exception | None = None) -> None:
        self._result = result if result is not None else []
        self._exception = exception
        self.call_count = 0
        self.received_event_types: list[tuple] = []

    def fetch_events(self, event_types):
        self.call_count += 1
        self.received_event_types.append(event_types)
        if self._exception is not None:
            raise self._exception
        return list(self._result)


class FakeRepository:
    """In-memory repository stub with call tracking."""

    def __init__(self, already_synced: bool = False) -> None:
        self._already_synced = already_synced
        self.save_events_calls: list[list] = []
        self.mark_synced_calls: list[tuple] = []
        self.has_synced_calls: list[tuple] = []

    def has_synced_for_date(self, sync_date, event_types, source="stockbit"):
        self.has_synced_calls.append((sync_date, event_types, source))
        return self._already_synced

    def mark_synced(self, sync_date, event_types, status, source="stockbit"):
        self.mark_synced_calls.append((sync_date, event_types, status, source))

    def save_events(self, events):
        self.save_events_calls.append(list(events))


def _run(provider: FakeProvider, repository: FakeRepository, force: bool = False):
    uc = SyncCorporateActionCalendarUseCase(provider=provider, repository=repository)
    return uc.execute(
        SyncCorporateActionCalendarRequest(
            event_types=_DIVIDEND_IPO,
            sync_date=_TODAY,
            force_remote_fetch=force,
        )
    )


class TestCachedShortCircuit:
    def test_already_synced_and_not_forced_returns_cached_without_calling_provider(self):
        provider = FakeProvider(result=[_event()])
        repository = FakeRepository(already_synced=True)
        response = _run(provider, repository, force=False)

        assert response.status == "cached"
        assert response.from_cache is True
        assert provider.call_count == 0
        assert repository.save_events_calls == []
        assert repository.mark_synced_calls == []

    def test_force_remote_fetch_bypasses_marker_check_entirely(self):
        provider = FakeProvider(result=[_event()])
        repository = FakeRepository(already_synced=True)
        response = _run(provider, repository, force=True)

        assert response.status == "success"
        assert response.from_cache is False
        assert provider.call_count == 1


class TestFullSuccess:
    def test_full_success_saves_all_and_marks_success(self):
        events = [
            _event(event_type=CorporateActionType.DIVIDEND, source_event_id="d1"),
            _event(event_type=CorporateActionType.IPO, source_event_id="i1"),
        ]
        provider = FakeProvider(result=events)
        repository = FakeRepository(already_synced=False)
        response = _run(provider, repository)

        assert response.status == "success"
        assert response.from_cache is False
        assert response.fetched_count == 2
        assert response.stored_count == 2
        assert response.event_type_counts == {"dividend": 1, "ipo": 1}
        assert response.errors == ()
        assert repository.save_events_calls == [events]
        assert repository.mark_synced_calls == [(_TODAY, _DIVIDEND_IPO, "success", "stockbit")]

    def test_empty_but_successful_fetch_still_marks_synced_without_saving(self):
        """Subtle branch: provider returns [] with no error → status is still
        'success' and mark_synced IS called, even though save_events is
        skipped (there's nothing to save)."""
        provider = FakeProvider(result=[])
        repository = FakeRepository(already_synced=False)
        response = _run(provider, repository)

        assert response.status == "success"
        assert response.stored_count == 0
        assert response.fetched_count == 0
        assert repository.save_events_calls == []  # nothing to save
        assert repository.mark_synced_calls == [(_TODAY, _DIVIDEND_IPO, "success", "stockbit")]


class TestPartialFailure:
    def test_partial_failure_saves_partial_data_and_marks_partial(self):
        partial_events = [_event(event_type=CorporateActionType.DIVIDEND, source_event_id="d1")]
        error = CorporateActionCalendarFetchError(
            partial_events=partial_events,
            failed_event_types=(CorporateActionType.IPO,),
            reason_by_type={CorporateActionType.IPO: "auth-or-network"},
        )
        provider = FakeProvider(exception=error)
        repository = FakeRepository(already_synced=False)
        response = _run(provider, repository)

        assert response.status == "partial"
        assert repository.save_events_calls == [partial_events]
        assert repository.mark_synced_calls == [(_TODAY, _DIVIDEND_IPO, "partial", "stockbit")]
        assert response.errors == ("ipo:auth-or-network",)

    def test_partial_with_empty_partial_events_is_total_failure(self):
        """Everything failed (partial_events=[]) → status='failed', NO save,
        NO mark — even though a CorporateActionCalendarFetchError was raised."""
        error = CorporateActionCalendarFetchError(
            partial_events=[],
            failed_event_types=_DIVIDEND_IPO,
            reason_by_type={
                CorporateActionType.DIVIDEND: "auth-or-network",
                CorporateActionType.IPO: "auth-or-network",
            },
        )
        provider = FakeProvider(exception=error)
        repository = FakeRepository(already_synced=False)
        response = _run(provider, repository)

        assert response.status == "failed"
        assert repository.save_events_calls == []
        assert repository.mark_synced_calls == []


class TestTotalFailure:
    def test_plain_exception_is_total_failure_no_save_no_mark(self):
        provider = FakeProvider(exception=RuntimeError("network down"))
        repository = FakeRepository(already_synced=False)
        response = _run(provider, repository)

        assert response.status == "failed"
        assert response.fetched_count == 0
        assert response.stored_count == 0
        assert repository.save_events_calls == []
        assert repository.mark_synced_calls == []
        assert response.errors == ("network down",)


class TestSelfHealing:
    """Verified end-to-end against the REAL SQLite repository, since this is
    the has_synced_for_date/mark_synced contract — an in-memory fake would
    not exercise the actual SQL semantics."""

    @pytest.fixture
    def real_repo(self, tmp_path: Path) -> SQLiteCorporateActionCalendarRepository:
        return SQLiteCorporateActionCalendarRepository(tmp_path / "calendar.db")

    def test_partial_mark_does_not_short_circuit_next_non_forced_call(self, real_repo):
        error = CorporateActionCalendarFetchError(
            partial_events=[_event(event_type=CorporateActionType.DIVIDEND, source_event_id="d1")],
            failed_event_types=(CorporateActionType.IPO,),
            reason_by_type={CorporateActionType.IPO: "auth-or-network"},
        )
        provider = FakeProvider(exception=error)
        uc = SyncCorporateActionCalendarUseCase(provider=provider, repository=real_repo)

        first = uc.execute(
            SyncCorporateActionCalendarRequest(event_types=_DIVIDEND_IPO, sync_date=_TODAY, force_remote_fetch=False)
        )
        assert first.status == "partial"

        # Second call, still not forced — must retry (not short-circuit to cached)
        # because "partial" doesn't count as synced.
        second_provider = FakeProvider(result=[_event(event_type=CorporateActionType.IPO, source_event_id="i1")])
        uc2 = SyncCorporateActionCalendarUseCase(provider=second_provider, repository=real_repo)
        second = uc2.execute(
            SyncCorporateActionCalendarRequest(event_types=_DIVIDEND_IPO, sync_date=_TODAY, force_remote_fetch=False)
        )
        assert second.status != "cached"
        assert second_provider.call_count == 1

    def test_success_mark_does_short_circuit_next_call(self, real_repo):
        provider = FakeProvider(result=[_event()])
        uc = SyncCorporateActionCalendarUseCase(provider=provider, repository=real_repo)
        first = uc.execute(
            SyncCorporateActionCalendarRequest(event_types=_DIVIDEND_IPO, sync_date=_TODAY, force_remote_fetch=False)
        )
        assert first.status == "success"

        second_provider = FakeProvider(result=[_event()])
        uc2 = SyncCorporateActionCalendarUseCase(provider=second_provider, repository=real_repo)
        second = uc2.execute(
            SyncCorporateActionCalendarRequest(event_types=_DIVIDEND_IPO, sync_date=_TODAY, force_remote_fetch=False)
        )
        assert second.status == "cached"
        assert second_provider.call_count == 0

    def test_different_event_type_subsets_get_independent_sync_keys(self, real_repo):
        provider = FakeProvider(result=[_event()])
        uc = SyncCorporateActionCalendarUseCase(provider=provider, repository=real_repo)
        uc.execute(
            SyncCorporateActionCalendarRequest(event_types=_DIVIDEND_IPO, sync_date=_TODAY, force_remote_fetch=False)
        )

        rups_provider = FakeProvider(result=[_event(event_type=CorporateActionType.RUPS, source_event_id="r1")])
        uc2 = SyncCorporateActionCalendarUseCase(provider=rups_provider, repository=real_repo)
        response = uc2.execute(
            SyncCorporateActionCalendarRequest(
                event_types=(CorporateActionType.RUPS,), sync_date=_TODAY, force_remote_fetch=False
            )
        )
        # (RUPS,) was never marked synced, so it must actually fetch (not cached).
        assert response.status != "cached"
        assert rups_provider.call_count == 1

    def test_same_subset_different_order_collapses_to_same_sync_key(self, real_repo):
        provider = FakeProvider(result=[_event()])
        uc = SyncCorporateActionCalendarUseCase(provider=provider, repository=real_repo)
        uc.execute(
            SyncCorporateActionCalendarRequest(
                event_types=(CorporateActionType.DIVIDEND, CorporateActionType.IPO),
                sync_date=_TODAY,
                force_remote_fetch=False,
            )
        )

        reordered_provider = FakeProvider(result=[_event()])
        uc2 = SyncCorporateActionCalendarUseCase(provider=reordered_provider, repository=real_repo)
        response = uc2.execute(
            SyncCorporateActionCalendarRequest(
                event_types=(CorporateActionType.IPO, CorporateActionType.DIVIDEND),
                sync_date=_TODAY,
                force_remote_fetch=False,
            )
        )
        assert response.status == "cached"
        assert reordered_provider.call_count == 0
