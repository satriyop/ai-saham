"""Tests for RecordAccumulationObservationsUseCase — ADR-056 multi-window persist."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
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
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AccumPopulationBinding
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
    session_dates = _weekdays(date(2026, 1, 1), 100)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 10, 1) + timedelta(days=i), Decimal("100")) for i in range(120)
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


def test_execute_is_screen_only_does_not_persist():
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

    assert result.recorded_count == 0
    assert len(spy_repo.saved) == 0
    assert len(result.response.candidates) == 1


def test_persist_multi_window_writes_one_session_observation():
    spy_repo = SpyCandidateObservationsRepository()
    bundle, as_of = _build_bundle(spy_repo)
    ctx = _context(as_of)
    recorder = bundle.record_observations_use_case

    window_results = {}
    for window in (7, 30, 90):
        req = AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=window,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
        response = recorder.screen(req, execution_context=ctx)
        window_results[window] = (req, list(response.observation_candidates))

    saved = recorder.persist_multi_window(
        window_results=window_results,
        snapshot_date=as_of,
        execution_context=ctx,
        universe_tickers=["BBCA"],
        population_binding=AccumPopulationBinding.create(
            membership_tickers=["BBCA"],
            named_universe_tickers=["ASII", "BBCA", "BBRI"],
            membership_session=as_of,
            pit_tradable_lookback_sessions=10,
            producer_source_revision="ai-saham@test",
        ),
        canonical_window=7,
    )

    assert saved == 1
    assert len(spy_repo.saved) == 1
    obs = spy_repo.saved[0]
    assert obs.window_id == f"BBCA:{as_of.isoformat()}"
    assert obs.horizon_contract == "accum_10d"
    payload = dict(obs.decision_payload)
    assert payload["artifact_type"] == "accumulation_session_observation"
    assert set(payload["features_by_window"]) == {"7", "30", "90"}
    assert float(payload["shared"]["current_price"]) > 0


def test_screen_use_case_execute_is_read_only():
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
