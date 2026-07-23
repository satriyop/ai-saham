"""Persister integration tests for observation_risk_assessments child rows."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case_bundle,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_observation_risk_assessment_repository import (
    SQLiteObservationRiskAssessmentRepository,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    _candle,
    _summary,
    _weekdays,
    make_signal_evidence_execution_context,
)


def _build_screen_bundle(
    tmp_path: Path,
    *,
    broker_repo,
    market_repo,
    with_risk: bool,
):
    observations_repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    SQLiteObservationRiskAssessmentRepository(tmp_path / "data.db")
    risk_use_case = None
    if with_risk:
        from src.adapters.cli.accumulation_risk_workflow_factory import (
            create_accumulation_assess_risk_use_case,
        )

        risk_use_case = create_accumulation_assess_risk_use_case(
            market_repository=market_repo,
        )
    return create_accumulation_screen_use_case_bundle(
        broker_repository=broker_repo,
        market_repository=market_repo,
        indicator_registry=IndicatorRegistry(),
        rules_loader=FakeRulesLoader(),
        risk_use_case=risk_use_case,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
        candidate_observations_repository=observations_repo,
    ), observations_repo


def test_survivor_with_risk_writes_child_row(tmp_path: Path) -> None:
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    broker_repo = MockBrokerRepository(summaries)
    market_repo = MockMarketRepository(candles)

    bundle, observations_repo = _build_screen_bundle(
        tmp_path,
        broker_repo=broker_repo,
        market_repo=market_repo,
        with_risk=True,
    )
    risk_repo = SQLiteObservationRiskAssessmentRepository(tmp_path / "data.db")
    request = AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        as_of_date=as_of,
    )
    context = make_signal_evidence_execution_context(as_of)
    result = bundle.record_observations_use_case.execute(request, execution_context=context)

    assert result.recorded_count == 1
    assert len(result.response.candidates) == 1
    assert result.response.candidates[0].risk_assessment is not None

    parent = observations_repo.get_latest("BBCA", as_of)
    assert parent is not None
    assert parent.payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION

    child = risk_repo.get_by_identity(
        ticker=parent.ticker,
        snapshot_date=parent.snapshot_date,
        workflow=parent.workflow,
        window_sessions=parent.window_sessions,
        data_as_of_date=parent.data_as_of_date,
        config_hash=parent.config_hash,
    )
    assert child is not None
    assert child.risk_assessment_json["gate_triggered"] == (
        result.response.candidates[0].risk_assessment.gate_triggered
    )
    assert child.risk_assessment_json["indicators"]["sma"] is not None


def test_rejected_candidate_without_risk_writes_no_child_row(tmp_path: Path) -> None:
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    broker_repo = MockBrokerRepository(summaries)
    market_repo = MockMarketRepository(candles)

    bundle, observations_repo = _build_screen_bundle(
        tmp_path,
        broker_repo=broker_repo,
        market_repo=market_repo,
        with_risk=True,
    )
    risk_repo = SQLiteObservationRiskAssessmentRepository(tmp_path / "data.db")
    request = AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        as_of_date=as_of,
        min_accum_score=9999.0,
        min_accum_score_enabled=True,
    )
    context = make_signal_evidence_execution_context(as_of)
    result = bundle.record_observations_use_case.execute(request, execution_context=context)

    assert result.recorded_count == 1
    assert len(result.response.candidates) == 0

    parent = observations_repo.get_latest("BBCA", as_of)
    assert parent is not None
    assert parent.payload["screen_result"] == "rejected_flow"

    child = risk_repo.get_by_identity(
        ticker=parent.ticker,
        snapshot_date=parent.snapshot_date,
        workflow=parent.workflow,
        window_sessions=parent.window_sessions,
        data_as_of_date=parent.data_as_of_date,
        config_hash=parent.config_hash,
    )
    assert child is None
