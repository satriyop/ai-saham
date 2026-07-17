"""Tests for SwingAnalysisInputCollector date threading.

Focused proof that ``request.today`` reaches the accumulation-candidate builder
so historical ``--date`` mode stays internally consistent.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.services.swing_analysis_input_collector import (
    SwingAnalysisInputCollector,
)


def _request(today: date) -> SwingAnalysisWorkflowRequest:
    return SwingAnalysisWorkflowRequest(
        ticker="BBRI",
        today=today,
        strategy_name=None,
        setup_name=None,
        window=200,
        flow_window=20,
        capital=None,
        risk_pct=1.0,
        entry_price=None,
        atr_mult=2.0,
        rr=2.0,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
        sentiment_verbose=False,
        auto_refresh=False,
        force_refresh=False,
        with_market_context=False,
        regime_universe="lq45",
        benchmark="COMPOSITE",
        db_path=Path("/tmp/does-not-exist.db"),
    )


def _fake_effective_session(today: date):
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )

    return EffectiveMarketSession(
        run_at=datetime(today.year, today.month, today.day, 20, 0),
        decision_at=datetime(today.year, today.month, today.day, 20, 0),
        latest_completed_session=today,
        analysis_as_of=today,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _collector_for_availability_tests(
    *,
    accumulation_candidate,
    trading_session_calendar_loader=None,
    today: date,
):
    market_repo = SimpleNamespace(
        get_candles=lambda ticker, end_date=None: [
            SimpleNamespace(close=100.0, date=today)
        ]
    )
    return SwingAnalysisInputCollector(
        market_repository=market_repo,
        broker_repository=SimpleNamespace(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate=lambda **kwargs: accumulation_candidate,
        evaluate_market_context=None,
        session_resolver=SimpleNamespace(resolve=lambda **kwargs: _fake_effective_session(today)),
        trading_session_calendar_loader=trading_session_calendar_loader,
    )


def test_source_availability_assessed_when_candidate_present():
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus

    today = date(2026, 7, 17)
    candidate = SimpleNamespace(latest_broker_date=today, latest_broker_daily_flow_date=today)

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        return KnownTradingSessionCalendar(
            sessions=(today,), coverage_start=coverage_start, coverage_end=coverage_end
        )

    collector = _collector_for_availability_tests(
        accumulation_candidate=candidate,
        trading_session_calendar_loader=calendar_loader,
        today=today,
    )
    state = collector.collect(_request(today))

    assert state.setup_source_availability is not None
    assert state.setup_source_availability.assessments[0].status == SourceAvailabilityStatus.CURRENT
    assert state.flow_source_availability is not None


def test_source_availability_none_when_no_candidate():
    today = date(2026, 7, 17)
    collector = _collector_for_availability_tests(
        accumulation_candidate=None, trading_session_calendar_loader=None, today=today
    )
    state = collector.collect(_request(today))

    assert state.setup_source_availability is None
    assert state.flow_source_availability is None


def test_calendar_loader_invoked_exactly_once_per_workflow_execution():
    today = date(2026, 7, 17)
    candidate = SimpleNamespace(latest_broker_date=today, latest_broker_daily_flow_date=today)
    calls: list[tuple] = []

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        calls.append((coverage_start, coverage_end))
        return KnownTradingSessionCalendar(
            sessions=(today,), coverage_start=coverage_start, coverage_end=coverage_end
        )

    collector = _collector_for_availability_tests(
        accumulation_candidate=candidate,
        trading_session_calendar_loader=calendar_loader,
        today=today,
    )
    collector.collect(_request(today))

    assert len(calls) == 1


def test_calendar_window_is_minimal_not_a_fixed_lookback():
    # The calendar window must be the smallest range that can prove the
    # session gaps this decision actually needs — min(observed source
    # date)..latest_completed_session — not an arbitrary fixed lookback
    # (e.g. 60 calendar days) that risks hitting an unrelated gap elsewhere
    # in a wider range and failing closed for no reason.
    today = date(2026, 7, 17)
    lagged_broker_date = date(2026, 7, 10)  # the oldest observed source date
    candidate = SimpleNamespace(
        latest_broker_date=lagged_broker_date,
        latest_broker_daily_flow_date=lagged_broker_date,
    )
    calls: list[tuple] = []

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        calls.append((coverage_start, coverage_end))
        return KnownTradingSessionCalendar(
            sessions=(today, lagged_broker_date),
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

    collector = _collector_for_availability_tests(
        accumulation_candidate=candidate,
        trading_session_calendar_loader=calendar_loader,
        today=today,
    )
    collector.collect(_request(today))

    assert len(calls) == 1
    coverage_start, coverage_end = calls[0]
    # candles observed_through is `today` (the fake market_repo fixture), the
    # oldest observed source date is lagged_broker_date — the window must
    # start there, not 60 days back from `today`.
    assert coverage_start == lagged_broker_date
    assert coverage_end == today  # latest_completed_session from the fake session


def test_missing_calendar_loader_falls_back_to_unknown_not_a_crash():
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus

    today = date(2026, 7, 17)
    candidate = SimpleNamespace(latest_broker_date=today, latest_broker_daily_flow_date=today)
    collector = _collector_for_availability_tests(
        accumulation_candidate=candidate, trading_session_calendar_loader=None, today=today
    )

    state = collector.collect(_request(today))

    assert state.setup_source_availability is not None
    assert state.setup_source_availability.assessments[0].status == SourceAvailabilityStatus.UNKNOWN


def test_accumulation_builder_receives_request_today():
    # A fixed historical date that is NOT date.today().
    historical = date(2025, 1, 15)
    assert historical != date.today()

    received: dict = {}

    def build_accumulation_candidate(**kwargs):
        received.update(kwargs)
        return None

    market_repo = SimpleNamespace(
        get_candles=lambda ticker, end_date=None: [SimpleNamespace(close=100.0)]
    )
    # This test proves request.today threading into the accumulation
    # builder, not effective-session resolution — inject a fake resolver so
    # the real resolver's IHSG get_candles(end_date=...) lookup (which this
    # market_repo fake does not implement) is never invoked.
    collector = SwingAnalysisInputCollector(
        market_repository=market_repo,
        broker_repository=SimpleNamespace(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate=build_accumulation_candidate,
        evaluate_market_context=None,
        session_resolver=SimpleNamespace(resolve=lambda **kwargs: None),
    )

    collector.collect(_request(historical))

    assert received["as_of_date"] == historical
    assert received["ticker"] == "BBRI"
    assert received["window"] == 200
