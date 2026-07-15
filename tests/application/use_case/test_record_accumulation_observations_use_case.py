"""Tests for RecordAccumulationObservationsUseCase — the sole intentional
entrypoint for persisting accumulation-screen candidate observations."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case_bundle,
)
from src.application.services.indicator_registry import IndicatorRegistry
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
