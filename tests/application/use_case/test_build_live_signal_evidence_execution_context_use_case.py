from datetime import date, datetime, timedelta

import pytest

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.build_live_signal_evidence_execution_context_use_case import (
    BuildLiveSignalEvidenceExecutionContextUseCase,
)
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


def _run_at(day: date) -> datetime:
    return datetime.combine(day, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)


def test_resolver_receives_exact_run_at():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
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
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert len(resolver.run_at_calls) == 1


def test_context_builder_called_exactly_once():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert len(builder.calls) == 1


def test_context_builder_receives_exact_session_from_resolver():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert builder.calls[0]["effective_session"] is session


def test_coverage_end_prefers_latest_completed_session():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 16),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert builder.calls[0]["coverage_end"] == date(2026, 7, 16)


def test_coverage_end_uses_analysis_as_of_when_latest_completed_session_absent():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=None,
        analysis_as_of=date(2026, 7, 15),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert builder.calls[0]["coverage_end"] == date(2026, 7, 15)


def test_coverage_end_uses_decision_at_date_when_both_absent():
    decision_at = _run_at(date(2026, 7, 17))
    session = _session(
        decision_at=decision_at,
        latest_completed_session=None,
        analysis_as_of=None,
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=decision_at)

    assert builder.calls[0]["coverage_end"] == decision_at.date()


def test_coverage_start_is_fourteen_days_before_coverage_end():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    call = builder.calls[0]
    assert call["coverage_start"] == call["coverage_end"] - timedelta(days=14)


def test_returns_exact_context_object_from_builder():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    sentinel_context = object()
    resolver = RecordingSessionResolver(session)
    builder = RecordingContextBuilder(sentinel_context)
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    result = use_case.execute(run_at=_run_at(date(2026, 7, 17)))

    assert result is sentinel_context


def test_value_error_from_resolver_propagates():
    resolver = RaisingSessionResolver(ValueError("bad run_at"))
    builder = RecordingContextBuilder(object())
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    with pytest.raises(ValueError, match="bad run_at"):
        use_case.execute(run_at=_run_at(date(2026, 7, 17)))


def test_value_error_from_context_builder_propagates():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RaisingContextBuilder(ValueError("bad coverage"))
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    with pytest.raises(ValueError, match="bad coverage"):
        use_case.execute(run_at=_run_at(date(2026, 7, 17)))


def test_type_error_from_context_builder_propagates():
    session = _session(
        decision_at=_run_at(date(2026, 7, 17)),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 17),
    )
    resolver = RecordingSessionResolver(session)
    builder = RaisingContextBuilder(TypeError("bad types"))
    use_case = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=resolver, context_builder=builder
    )

    with pytest.raises(TypeError, match="bad types"):
        use_case.execute(run_at=_run_at(date(2026, 7, 17)))
