"""Tests for RecordAccumulationObservationsUseCase — the sole intentional
entrypoint for persisting accumulation-screen candidate observations."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case_bundle,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
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
        )
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
        )
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
        )
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
        )
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
        effective_session=session,
    )

    assert result.recorded_count == 1
    assert len(spy_repo.saved) == 1
    saved = spy_repo.saved[0]
    assert saved.decision_at == session.decision_at
    assert saved.latest_completed_session == session.latest_completed_session
    assert saved.analysis_as_of == session.analysis_as_of
    assert saved.market_session_name == session.market_session_name
    assert saved.is_eod_pending == session.is_eod_pending
    assert saved.resolution_source == session.resolution_source
    assert saved.resolution_notes == session.notes


def test_no_effective_session_leaves_provenance_fields_empty():
    """Legacy/direct callers that don't pass effective_session must still
    work — new fields default to None/empty, no resolution attempted."""
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)

    result = bundle.record_observations_use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert result.recorded_count == 1
    saved = spy_repo.saved[0]
    assert saved.decision_at is None
    assert saved.latest_completed_session is None
    assert saved.analysis_as_of is None
    assert saved.market_session_name is None
    assert saved.is_eod_pending is None
    assert saved.resolution_source is None
    assert saved.resolution_notes == ()
