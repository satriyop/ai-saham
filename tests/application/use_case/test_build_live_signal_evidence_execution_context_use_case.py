from datetime import date, datetime, timedelta

import pytest

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.build_live_signal_evidence_execution_context_use_case import (
    BuildLiveSignalEvidenceExecutionContextUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE


def _session(
    *,
    decision_at: datetime,
    latest_completed_session: date | None,
    analysis_as_of: date | None,
) -> EffectiveMarketSession:
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=latest_completed_session,
        analysis_as_of=analysis_as_of,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
    )


class RecordingSessionResolver:
    def __init__(self, session: EffectiveMarketSession):
        self._session = session
        self.run_at_calls: list[datetime] = []

    def resolve(self, *, run_at: datetime) -> EffectiveMarketSession:
        self.run_at_calls.append(run_at)
        return self._session


class RaisingSessionResolver:
    def __init__(self, exc: Exception):
        self._exc = exc

    def resolve(self, *, run_at: datetime) -> EffectiveMarketSession:
        raise self._exc


class RecordingContextBuilder:
    def __init__(self, context: object):
        self._context = context
        self.calls: list[dict] = []

    def build(self, *, effective_session, coverage_start, coverage_end):
        self.calls.append(
            {
                "effective_session": effective_session,
                "coverage_start": coverage_start,
                "coverage_end": coverage_end,
            }
        )
        return self._context


class RaisingContextBuilder:
    def __init__(self, exc: Exception):
        self._exc = exc

    def build(self, *, effective_session, coverage_start, coverage_end):
        raise self._exc


class FakeMarketRepository:
    """Minimal IHSG candle source for coverage-window selection."""

    def __init__(self, sessions: tuple[date, ...]):
        self._sessions = sessions

    def get_candles(self, ticker, start_date=None, end_date=None):
        assert ticker == "IHSG"
        rows = []
        for day in self._sessions:
            if start_date is not None and day < start_date:
                continue
            if end_date is not None and day > end_date:
                continue
            rows.append(
                Candle(
                    ticker="IHSG",
                    date=day,
                    open=100,
                    high=100,
                    low=100,
                    close=100,
                    volume=1000,
                )
            )
        return rows


def _run_at(day: date) -> datetime:
    return datetime.combine(day, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)


def _weekdays(start: date, count: int) -> tuple[date, ...]:
    days: list[date] = []
    cur = start
    while len(days) < count:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return tuple(days)


def _use_case(*, session, builder, sessions=None):
    if sessions is None:
        end = session.latest_completed_session or session.decision_at.date()
        sessions = _weekdays(end - timedelta(days=20), 15)
    return BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session)
        if isinstance(session, EffectiveMarketSession)
        else session,
        context_builder=builder,
        market_data_repository=FakeMarketRepository(sessions),
    )


def test_resolver_receives_exact_run_at():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver,
        context_builder=builder,
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    run_at = _run_at(date(2026, 7, 17))
    use_case.execute(run_at=run_at)

    assert resolver.run_at_calls == [run_at]


def test_resolver_called_exactly_once():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver,
        context_builder=builder,
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert len(resolver.run_at_calls) == 1


def test_coverage_end_uses_latest_completed_session():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 16),
        analysis_as_of=date(2026, 7, 17),
    )
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=builder,
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert builder.calls[0]["coverage_end"] == date(2026, 7, 16)


def test_coverage_end_falls_back_to_analysis_as_of():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=None,
        analysis_as_of=date(2026, 7, 15),
    )
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=builder,
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert builder.calls[0]["coverage_end"] == date(2026, 7, 15)


def test_coverage_end_falls_back_to_decision_date():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=None,
        analysis_as_of=None,
    )
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=builder,
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert builder.calls[0]["coverage_end"] == date(2026, 7, 17)


def test_coverage_start_is_gap_free_session_lookback_not_fixed_fourteen_days():
    # Gap-free Mon-Fri week ending 2026-07-17: lookback is session-capped
    # (max 5), not a fixed 14 calendar days that would reach into prior weeks.
    sessions = (
        date(2026, 7, 13),
        date(2026, 7, 14),
        date(2026, 7, 15),
        date(2026, 7, 16),
        date(2026, 7, 17),
    )
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=builder,
        market_data_repository=FakeMarketRepository(sessions),
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    call = builder.calls[0]
    assert call["coverage_end"] == date(2026, 7, 17)
    assert call["coverage_start"] == date(2026, 7, 13)
    assert call["coverage_start"] != call["coverage_end"] - timedelta(days=14)


def test_coverage_start_shrinks_around_holiday_weekday_gap():
    # 2026-06-16 missing (IDX holiday). Long lookback would fail provider;
    # gap-free helper must stop before the hole.
    sessions = (
        date(2026, 6, 12),
        date(2026, 6, 15),
        # 2026-06-16 absent
        date(2026, 6, 17),
        date(2026, 6, 18),
        date(2026, 6, 19),
    )
    session = _session(
        decision_at=_run_at(date(2026, 6, 19)),
        latest_completed_session=date(2026, 6, 19),
        analysis_as_of=date(2026, 6, 19),
    )
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=builder,
        market_data_repository=FakeMarketRepository(sessions),
    )

    use_case.execute(run_at=_run_at(date(2026, 6, 19)))

    call = builder.calls[0]
    assert call["coverage_end"] == date(2026, 6, 19)
    assert call["coverage_start"] == date(2026, 6, 17)


def test_returns_exact_context_object_from_builder():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    sentinel_context = object()
    builder = RecordingContextBuilder(sentinel_context)
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=builder,
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    result = use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert result is sentinel_context


def test_value_error_from_resolver_propagates():
    resolver = RaisingSessionResolver(ValueError("bad run_at"))
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver,
        context_builder=builder,
        market_data_repository=FakeMarketRepository(()),
    )

    with pytest.raises(ValueError, match="bad run_at"):
        use_case.execute(run_at=_run_at(date(2026, 7, 17)))


def test_type_error_from_resolver_propagates():
    resolver = RaisingSessionResolver(TypeError("bad type"))
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver,
        context_builder=builder,
        market_data_repository=FakeMarketRepository(()),
    )

    with pytest.raises(TypeError, match="bad type"):
        use_case.execute(run_at=_run_at(date(2026, 7, 17)))


def test_value_error_from_builder_propagates():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=RecordingSessionResolver(session),
        context_builder=RaisingContextBuilder(ValueError("bad window")),
        market_data_repository=FakeMarketRepository(_weekdays(date(2026, 7, 1), 15)),
    )

    with pytest.raises(ValueError, match="bad window"):
        use_case.execute(run_at=_run_at(date(2026, 7, 17)))
