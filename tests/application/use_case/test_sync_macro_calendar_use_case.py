"""
Tests for SyncMacroCalendarUseCase — cache-aware macro calendar sync.
"""

from datetime import date
from pathlib import Path

import pytest

from src.application.ports.macro_calendar_provider import MacroCalendarFetchError
from src.application.use_case.sync_macro_calendar_use_case import (
    SyncMacroCalendarRequest,
    SyncMacroCalendarUseCase,
)
from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)
from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
    SQLiteMacroCalendarRepository,
)

_TODAY = date(2026, 7, 11)


def _event(
    source_event_id: str = "e1",
    category: MacroEventCategory = MacroEventCategory.OTHER,
) -> MacroCalendarEvent:
    return MacroCalendarEvent(
        source_event_id=source_event_id,
        event_date=_TODAY,
        category=category,
        title=f"Event {source_event_id}",
        raw_payload_json="{}",
        fetched_at=_TODAY.isoformat(),
    )


class FakeProvider:
    def __init__(self, result=None, exception: Exception | None = None) -> None:
        self._result = result if result is not None else []
        self._exception = exception
        self.call_count = 0

    def fetch_events(self):
        self.call_count += 1
        if self._exception is not None:
            raise self._exception
        return list(self._result)


class FakeRepository:
    def __init__(self, already_synced: bool = False) -> None:
        self._already_synced = already_synced
        self.save_events_calls: list[list] = []
        self.mark_synced_calls: list[tuple] = []
        self.reclassify_calls: list = []
        self.reclassify_return = 0

    def has_synced_for_date(self, sync_date, source="stockbit"):
        return self._already_synced

    def mark_synced(self, sync_date, status, source="stockbit"):
        self.mark_synced_calls.append((sync_date, status, source))

    def save_events(self, events):
        self.save_events_calls.append(list(events))

    def get_events_in_window(self, *args, **kwargs):
        return []

    def reclassify_event_categories(self, category_for_title):
        self.reclassify_calls.append(category_for_title)
        return self.reclassify_return


def _run(
    provider: FakeProvider,
    repository: FakeRepository,
    force: bool = False,
    category_for_title=None,
):
    uc = SyncMacroCalendarUseCase(
        provider=provider,
        repository=repository,
        category_for_title=category_for_title,
    )
    return uc.execute(SyncMacroCalendarRequest(sync_date=_TODAY, force_remote_fetch=force))


class TestCachedShortCircuit:
    def test_already_synced_returns_cached_without_provider(self):
        provider = FakeProvider(result=[_event()])
        repository = FakeRepository(already_synced=True)
        response = _run(provider, repository, force=False)

        assert response.status == "cached"
        assert response.from_cache is True
        assert provider.call_count == 0
        assert repository.save_events_calls == []
        assert repository.mark_synced_calls == []
        assert repository.reclassify_calls == []
        assert response.reclassified_count == 0

    def test_cached_still_reclassifies_when_normalizer_injected(self):
        provider = FakeProvider(result=[_event()])
        repository = FakeRepository(already_synced=True)
        repository.reclassify_return = 8

        def _norm(title: str) -> MacroEventCategory:
            return MacroEventCategory.BI_RATE

        response = _run(provider, repository, force=False, category_for_title=_norm)

        assert response.status == "cached"
        assert provider.call_count == 0
        assert len(repository.reclassify_calls) == 1
        assert response.reclassified_count == 8

    def test_force_bypasses_marker(self):
        provider = FakeProvider(result=[_event()])
        repository = FakeRepository(already_synced=True)
        response = _run(provider, repository, force=True)

        assert response.status == "success"
        assert response.from_cache is False
        assert provider.call_count == 1


class TestFullSuccess:
    def test_success_saves_and_marks(self):
        events = [
            _event("b1", MacroEventCategory.BI_RATE),
            _event("c1", MacroEventCategory.INFLATION),
        ]
        provider = FakeProvider(result=events)
        repository = FakeRepository()
        response = _run(provider, repository)

        assert response.status == "success"
        assert response.fetched_count == 2
        assert response.stored_count == 2
        assert response.category_counts == {"bi_rate": 1, "inflation": 1}
        assert repository.save_events_calls == [events]
        assert repository.mark_synced_calls == [(_TODAY, "success", "stockbit")]

    def test_empty_successful_fetch_marks_without_saving(self):
        provider = FakeProvider(result=[])
        repository = FakeRepository()
        response = _run(provider, repository)

        assert response.status == "success"
        assert response.stored_count == 0
        assert repository.save_events_calls == []
        assert repository.mark_synced_calls == [(_TODAY, "success", "stockbit")]


class TestPartialAndFailure:
    def test_partial_with_events_marks_partial(self):
        partial = [_event("p1")]
        provider = FakeProvider(
            exception=MacroCalendarFetchError("partial-source", partial_events=partial)
        )
        repository = FakeRepository()
        response = _run(provider, repository)

        assert response.status == "partial"
        assert repository.save_events_calls == [partial]
        assert repository.mark_synced_calls == [(_TODAY, "partial", "stockbit")]
        assert response.errors == ("partial-source",)

    def test_fetch_error_with_no_events_is_failed_no_mark(self):
        provider = FakeProvider(
            exception=MacroCalendarFetchError("auth-or-network", partial_events=[])
        )
        repository = FakeRepository()
        response = _run(provider, repository)

        assert response.status == "failed"
        assert repository.save_events_calls == []
        assert repository.mark_synced_calls == []

    def test_plain_exception_is_failed(self):
        provider = FakeProvider(exception=RuntimeError("network down"))
        repository = FakeRepository()
        response = _run(provider, repository)

        assert response.status == "failed"
        assert response.errors == ("network down",)
        assert repository.mark_synced_calls == []


class TestSelfHealingWithRealRepo:
    @pytest.fixture
    def real_repo(self, tmp_path: Path) -> SQLiteMacroCalendarRepository:
        return SQLiteMacroCalendarRepository(tmp_path / "macro.db")

    def test_success_short_circuits_next_call(self, real_repo):
        provider = FakeProvider(result=[_event()])
        uc = SyncMacroCalendarUseCase(provider=provider, repository=real_repo)
        first = uc.execute(SyncMacroCalendarRequest(sync_date=_TODAY))
        assert first.status == "success"

        second_provider = FakeProvider(result=[_event("e2")])
        uc2 = SyncMacroCalendarUseCase(provider=second_provider, repository=real_repo)
        second = uc2.execute(SyncMacroCalendarRequest(sync_date=_TODAY))
        assert second.status == "cached"
        assert second_provider.call_count == 0

    def test_partial_does_not_short_circuit(self, real_repo):
        provider = FakeProvider(exception=MacroCalendarFetchError("x", partial_events=[_event()]))
        uc = SyncMacroCalendarUseCase(provider=provider, repository=real_repo)
        first = uc.execute(SyncMacroCalendarRequest(sync_date=_TODAY))
        assert first.status == "partial"

        second_provider = FakeProvider(result=[_event("e2")])
        uc2 = SyncMacroCalendarUseCase(provider=second_provider, repository=real_repo)
        second = uc2.execute(SyncMacroCalendarRequest(sync_date=_TODAY))
        assert second.status != "cached"
        assert second_provider.call_count == 1
