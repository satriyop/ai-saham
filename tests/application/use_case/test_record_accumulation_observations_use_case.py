"""Tests for RecordAccumulationObservationsUseCase — the sole intentional
entrypoint for persisting accumulation-screen candidate observations."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
    AccumulationScreenResponse,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case_bundle,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.record_accumulation_observations_use_case import (
    RecordAccumulationObservationsUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
)

_LEAN_ID = SemanticCompatibilityId("sha256:" + "a" * 64)


def _context(
    as_of: date, session: EffectiveMarketSession | None = None
) -> SignalEvidenceExecutionContext:
    if session is None:
        now = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
        session = EffectiveMarketSession(
            run_at=now,
            decision_at=now,
            latest_completed_session=as_of,
            analysis_as_of=as_of,
            market_session_name="AFTER_CLOSE",
            is_eod_pending=False,
            resolution_source="ihsg_cache_same_day",
            notes=("a note",),
        )
    return SignalEvidenceExecutionContext(
        effective_session=session,
        source_availability_use_case=None,
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=_LEAN_ID,
    )


def _build_bundle(repo):
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    bundle = create_accumulation_screen_use_case_bundle(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    return bundle, as_of


def test_record_use_case_persists_and_returns_recorded_count():
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)

    result = bundle.record_observations_use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=_context(as_of),
    )

    assert result.recorded_count == 1
    assert len(spy_repo.saved) == 1
    assert len(result.response.candidates) == 1


def test_record_use_case_is_noop_when_no_repository():
    bundle, as_of = _build_bundle(None)

    result = bundle.record_observations_use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=_context(as_of),
    )

    assert result.recorded_count == 0
    assert len(result.response.candidates) == 1


def test_record_use_case_zero_tickers_records_zero_rows():
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)

    result = bundle.record_observations_use_case.execute(
        AccumulationScreenRequest(
            tickers=[],
            window_days=7,
            as_of_date=as_of,
        ),
        execution_context=_context(as_of),
    )

    assert result.recorded_count == 0
    assert result.response.candidates == []


def test_screen_use_case_execute_is_read_only_but_recorder_persists():
    """The screen use case and its recorder are separate collaborators —
    calling execute() directly must never persist, only the recorder does."""
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)

    response = bundle.screen_use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=_context(as_of),
    )

    assert len(response.candidates) == 1
    assert spy_repo.saved == []


def test_effective_session_passed_into_execute_is_persisted_on_every_observation():
    """DQ-002E: one EffectiveMarketSession passed into the recording path must
    land on every persisted CandidateObservation, verbatim."""
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)
    now = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
    session = EffectiveMarketSession(
        run_at=now,
        decision_at=now,
        latest_completed_session=as_of,
        analysis_as_of=as_of,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
        notes=("a note",),
    )

    result = bundle.record_observations_use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=_context(as_of, session),
    )

    assert result.recorded_count == 1
    assert len(spy_repo.saved) == 1
    provenance = spy_repo.saved[0].decision_payload["provenance"]
    assert provenance["decision_at"] == session.decision_at.isoformat()
    assert provenance["latest_completed_session"] == session.latest_completed_session.isoformat()
    assert provenance["analysis_as_of"] == session.analysis_as_of.isoformat()
    assert provenance["market_session_name"] == session.market_session_name
    assert provenance["is_eod_pending"] == session.is_eod_pending
    assert provenance["resolution_source"] == session.resolution_source
    assert provenance["resolution_notes"] == list(session.notes)


def test_no_effective_session_fails_closed():
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)

    empty_session = EffectiveMarketSession(
        run_at=datetime.min,
        decision_at=None,
        latest_completed_session=None,
        analysis_as_of=None,
        market_session_name=None,
        is_eod_pending=None,
        resolution_source=None,
    )
    context = SignalEvidenceExecutionContext(
        effective_session=empty_session,
        source_availability_use_case=None,
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=_LEAN_ID,
    )

    with pytest.raises(ValueError, match="requires completed-session provenance"):
        bundle.record_observations_use_case.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                window_days=7,
                min_net_buy_days=1,
                as_of_date=as_of,
            ),
            execution_context=context,
        )


def test_record_use_case_omitting_context_raises_type_error():
    import pytest

    bundle, as_of = _build_bundle(None)
    with pytest.raises(TypeError):
        # execute() requires execution_context as a mandatory keyword-only argument
        bundle.record_observations_use_case.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                window_days=7,
                min_net_buy_days=1,
                as_of_date=as_of,
            ),
        )


def test_screen_use_case_omitting_context_raises_type_error():
    import pytest

    bundle, as_of = _build_bundle(None)
    with pytest.raises(TypeError):
        # execute() requires execution_context as a mandatory keyword-only argument
        bundle.screen_use_case.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                window_days=7,
                min_net_buy_days=1,
                as_of_date=as_of,
            ),
        )


class _RecordingScreenFake:
    def __init__(self, response: AccumulationScreenResponse) -> None:
        self._response = response
        self.recorded_contexts: list[SignalEvidenceExecutionContext] = []

    def execute(
        self,
        request: AccumulationScreenRequest,
        *,
        execution_context: SignalEvidenceExecutionContext,
    ) -> AccumulationScreenResponse:
        self.recorded_contexts.append(execution_context)
        return self._response


class _RecordingPersister:
    def __init__(self) -> None:
        self.recorded_effective_sessions: list[EffectiveMarketSession] = []
        self.recorded_contracts: list[str | None] = []
        self.recorded_compat_ids: list[SemanticCompatibilityId | None] = []

    def persist(
        self,
        observation_candidates,
        screened_at,
        request,
        *,
        effective_session,
        observation_contract,
        semantic_compatibility_id,
    ):
        self.recorded_effective_sessions.append(effective_session)
        self.recorded_contracts.append(observation_contract)
        self.recorded_compat_ids.append(semantic_compatibility_id)
        return len(observation_candidates)


def test_recorder_passes_exact_context_to_screen_and_exact_session_to_persister():
    as_of = date(2026, 7, 16)
    context = _context(as_of)
    response = AccumulationScreenResponse(
        candidates=[],
        screened_at=as_of,
        window_days=7,
        total_tickers_checked=0,
        tickers_skipped=0,
        provider="idx",
        observation_candidates=[],
    )
    screen_fake = _RecordingScreenFake(response)
    persister = _RecordingPersister()
    recorder = RecordAccumulationObservationsUseCase(
        screen_use_case=screen_fake,
        observation_persister=persister,
    )

    result = recorder.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=context,
    )

    assert result.recorded_count == 0
    assert len(screen_fake.recorded_contexts) == 1
    assert screen_fake.recorded_contexts[0] is context

    assert len(persister.recorded_effective_sessions) == 1
    assert persister.recorded_effective_sessions[0] is context.effective_session

    # Transport chain: the record use case forwards the lean identity from the
    # execution context to the persister verbatim.
    assert persister.recorded_contracts == [context.observation_contract]
    assert persister.recorded_compat_ids == [context.semantic_compatibility_id]
