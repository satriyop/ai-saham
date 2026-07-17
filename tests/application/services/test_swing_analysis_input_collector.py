"""Tests for SwingAnalysisInputCollector date threading and the reused
AssessSourceAvailabilityUseCase construction (ADR-041 CANONICAL-EVIDENCE-
BOUNDARY).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.services.swing_analysis_input_collector import (
    SwingAnalysisInputCollector,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.domain.value_objects.canonical_signal_evidence_input import CandleRowIdentity, SetupProvenance


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


def _fake_effective_session(today: date, latest_completed_session: date | None = None):
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )

    session_date = latest_completed_session if latest_completed_session is not None else today
    return EffectiveMarketSession(
        run_at=datetime(today.year, today.month, today.day, 20, 0),
        decision_at=datetime(today.year, today.month, today.day, 20, 0),
        latest_completed_session=session_date,
        analysis_as_of=session_date,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _eval_result(
    *, broker_summary_date: date | None = None, broker_daily_flow_date: date | None = None
) -> SimpleNamespace:
    """Minimal stand-in for AccumulationCandidateEvaluationResult."""
    return SimpleNamespace(
        candidate=SimpleNamespace(ticker="BBRI"),
        consumed_candles=(),
        consumed_broker_summaries=(
            (SimpleNamespace(date=broker_summary_date),) if broker_summary_date is not None else ()
        ),
        consumed_broker_daily_flows=(
            (SimpleNamespace(date=broker_daily_flow_date),)
            if broker_daily_flow_date is not None
            else ()
        ),
    )


def _collector_for_availability_tests(
    *,
    accumulation_evaluation,
    trading_session_calendar_loader=None,
    today: date,
    candle_date: date | None = None,
    latest_completed_session: date | None = None,
):
    candle_date = candle_date if candle_date is not None else today
    market_repo = SimpleNamespace(
        get_candles=lambda ticker, end_date=None: [
            SimpleNamespace(close=100.0, date=candle_date)
        ]
    )
    builder = SignalEvidenceExecutionContextBuilder(
        trading_session_calendar_loader=trading_session_calendar_loader
    )
    return SwingAnalysisInputCollector(
        market_repository=market_repo,
        broker_repository=SimpleNamespace(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=lambda **kwargs: accumulation_evaluation,
        evaluate_market_context=None,
        session_resolver=SimpleNamespace(
            resolve=lambda **kwargs: _fake_effective_session(today, latest_completed_session)
        ),
        signal_evidence_context_builder=builder,
    )


def test_source_availability_use_case_built_when_collecting_input():
    # Actual per-source assessment now happens later, in
    # SwingAnalysisDecisionComposer.recompose_after_evidence, gated on
    # evidence actually existing — collect() only needs to build the reused
    # AssessSourceAvailabilityUseCase.
    today = date(2026, 7, 17)
    eval_result = _eval_result(broker_summary_date=today, broker_daily_flow_date=today)

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        return KnownTradingSessionCalendar(
            sessions=(today,), coverage_start=coverage_start, coverage_end=coverage_end
        )

    collector = _collector_for_availability_tests(
        accumulation_evaluation=eval_result,
        trading_session_calendar_loader=calendar_loader,
        today=today,
    )
    state = collector.collect(_request(today))

    # Assert that execution context is built and contains the availability assessor
    assert state.signal_evidence_execution_context is not None
    assert state.signal_evidence_execution_context.source_availability_use_case is not None
    # Canonical evidence groups are not assembled here.
    assert state.built_setup_evidence is None
    assert state.built_flow_evidence is None


def test_context_has_no_availability_assessor_when_calendar_loader_is_missing():
    # The context is still built when there is no accumulation candidate, but
    # source_availability_use_case is None here because
    # trading_session_calendar_loader is None — not because the candidate is
    # absent. Candidate presence/absence does not affect this outcome.
    today = date(2026, 7, 17)
    collector = _collector_for_availability_tests(
        accumulation_evaluation=None, trading_session_calendar_loader=None, today=today
    )
    state = collector.collect(_request(today))

    assert state.signal_evidence_execution_context is not None
    assert state.signal_evidence_execution_context.source_availability_use_case is None


def test_calendar_loader_invoked_exactly_once_per_workflow_execution():
    today = date(2026, 7, 17)
    eval_result = _eval_result(broker_summary_date=today, broker_daily_flow_date=today)
    calls: list[tuple] = []

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        calls.append((coverage_start, coverage_end))
        return KnownTradingSessionCalendar(
            sessions=(today,), coverage_start=coverage_start, coverage_end=coverage_end
        )

    collector = _collector_for_availability_tests(
        accumulation_evaluation=eval_result,
        trading_session_calendar_loader=calendar_loader,
        today=today,
    )
    collector.collect(_request(today))

    assert len(calls) == 1


def test_context_calendar_coverage_uses_eligible_candle_bounds():
    # coverage_start/coverage_end are derived from the collected candle
    # series (candles with date <= coverage_end), not from broker rows —
    # the current implementation never reads broker_summary_date or
    # broker_daily_flow_date to compute this window. This test sets
    # broker_summary_date/broker_daily_flow_date to an unrelated value to
    # prove they have no effect on the calculated bounds.
    today = date(2026, 7, 17)
    earliest_eligible_candle_date = date(2026, 7, 10)
    eval_result = _eval_result(
        broker_summary_date=date(2026, 1, 1), broker_daily_flow_date=date(2026, 1, 1)
    )
    calls: list[tuple] = []

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        calls.append((coverage_start, coverage_end))
        return KnownTradingSessionCalendar(
            sessions=(earliest_eligible_candle_date, today),
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

    collector = _collector_for_availability_tests(
        accumulation_evaluation=eval_result,
        trading_session_calendar_loader=calendar_loader,
        today=today,
        candle_date=earliest_eligible_candle_date,
    )
    collector.collect(_request(today))

    assert len(calls) == 1
    coverage_start, coverage_end = calls[0]
    # coverage_start is the earliest eligible candle date selected by the
    # current implementation (the fake market_repo returns a single candle
    # dated earliest_eligible_candle_date).
    assert coverage_start == earliest_eligible_candle_date
    # coverage_end is the effective session's latest completed session.
    assert coverage_end == today


def test_missing_calendar_loader_yields_typed_unknown_without_empty_calendar():
    from src.application.services.evidence_source_availability_assembler import (
        EvidenceSourceAvailabilityAssembler,
    )
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus

    today = date(2026, 7, 17)
    eval_result = _eval_result(broker_summary_date=today, broker_daily_flow_date=today)
    collector = _collector_for_availability_tests(
        accumulation_evaluation=eval_result, trading_session_calendar_loader=None, today=today
    )

    state = collector.collect(_request(today))

    # Context contains no availability use case — no empty calendar is
    # fabricated to stand in for the missing loader.
    assert state.signal_evidence_execution_context is not None
    assert state.signal_evidence_execution_context.source_availability_use_case is None

    # EvidenceSourceAvailabilityAssembler(None) produces typed UNKNOWN.
    provenance = SetupProvenance(
        ticker="BBRI",
        candle_rows=tuple(CandleRowIdentity(ticker="BBRI", date=c.date, source=None) for c in state.candles),
    )
    setup = EvidenceSourceAvailabilityAssembler(state.signal_evidence_execution_context.source_availability_use_case).assess_setup(
        effective_session=state.effective_session, provenance=provenance
    )
    assert setup.assessments[0].status == SourceAvailabilityStatus.UNKNOWN


def test_intraday_future_dated_observation_does_not_break_calendar_construction():
    # Reviewer's required scenario: an in-progress intraday candle dated
    # today while latest_completed_session is still yesterday. observed_dates
    # would include a date *after* coverage_end, which must not be allowed to
    # push coverage_start past coverage_end (that would break
    # KnownTradingSessionCalendar construction and silently drop the whole
    # diagnostic). The future-dated observation itself must still reach the
    # use case, which classifies it INVALID rather than dropping it.
    thursday = date(2026, 7, 16)
    friday = date(2026, 7, 17)  # today; also the "intraday" candle date
    eval_result = _eval_result(broker_summary_date=thursday, broker_daily_flow_date=thursday)
    calls: list[tuple] = []

    def calendar_loader(coverage_start, coverage_end):
        from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar

        calls.append((coverage_start, coverage_end))
        # The window is coverage_start=coverage_end=thursday (see assertion
        # below) — sessions must stay within that bound; friday (the
        # in-progress intraday candle date) is deliberately not a proven
        # session in this calendar, matching real life (today's session
        # isn't complete/proven yet).
        return KnownTradingSessionCalendar(
            sessions=(thursday,),
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

    collector = _collector_for_availability_tests(
        accumulation_evaluation=eval_result,
        trading_session_calendar_loader=calendar_loader,
        today=friday,
        candle_date=friday,
        latest_completed_session=thursday,
    )

    state = collector.collect(_request(friday))

    # Calendar construction succeeded — no "unavailable" warning, and the
    # window's lower bound excludes the future-dated candle rather than
    # producing coverage_start (friday) > coverage_end (thursday).
    assert not any("unavailable" in w.lower() for w in state.warnings)
    assert state.source_availability_use_case is not None
    coverage_start, coverage_end = calls[0]
    assert coverage_start == thursday
    assert coverage_end == thursday

    # The future-dated candle itself is still assessed — INVALID, not
    # dropped — once evidence assembly runs the actual check.
    from src.application.services.evidence_source_availability_assembler import (
        EvidenceSourceAvailabilityAssembler,
    )
    from src.domain.value_objects.source_availability import SourceAvailabilityStatus

    provenance = SetupProvenance(
        ticker="BBRI",
        candle_rows=tuple(CandleRowIdentity(ticker="BBRI", date=c.date, source=None) for c in state.candles),
    )
    setup = EvidenceSourceAvailabilityAssembler(state.source_availability_use_case).assess_setup(
        effective_session=state.effective_session, provenance=provenance
    )
    assert setup.assessments[0].status == SourceAvailabilityStatus.INVALID
    assert setup.assessments[0].is_authoritative is False


def test_accumulation_builder_receives_request_today():
    # A fixed historical date that is NOT date.today().
    historical = date(2025, 1, 15)
    assert historical != date.today()

    received: dict = {}

    def build_accumulation_candidate_evaluation(**kwargs):
        received.update(kwargs)
        return None

    market_repo = SimpleNamespace(
        get_candles=lambda ticker, end_date=None: [SimpleNamespace(close=100.0, date=historical)]
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
        build_accumulation_candidate_evaluation=build_accumulation_candidate_evaluation,
        evaluate_market_context=None,
        session_resolver=SimpleNamespace(resolve=lambda **kwargs: None),
        signal_evidence_context_builder=SignalEvidenceExecutionContextBuilder(
            trading_session_calendar_loader=None
        ),
    )

    collector.collect(_request(historical))

    assert received["as_of_date"] == historical
    assert received["ticker"] == "BBRI"
    assert received["window"] == 200


def test_collector_stores_exact_context_object_from_builder():
    from unittest.mock import MagicMock
    historical = date(2025, 1, 15)
    sentinel_context = MagicMock()
    builder_spy = MagicMock()
    builder_spy.build.return_value = sentinel_context

    market_repo = SimpleNamespace(
        get_candles=lambda ticker, end_date=None: [SimpleNamespace(close=100.0, date=historical)]
    )
    fake_session = _fake_effective_session(historical)

    candidate_builder_calls: list = []

    def recording_accumulation_candidate_builder(**kwargs):
        candidate_builder_calls.append(kwargs)
        return _eval_result(broker_summary_date=historical)

    collector = SwingAnalysisInputCollector(
        market_repository=market_repo,
        broker_repository=SimpleNamespace(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=recording_accumulation_candidate_builder,
        evaluate_market_context=None,
        session_resolver=SimpleNamespace(resolve=lambda **kwargs: fake_session),
        signal_evidence_context_builder=builder_spy,
    )

    state = collector.collect(_request(historical))

    # Assert build was called with the exact resolved session
    builder_spy.build.assert_called_once()
    assert builder_spy.build.call_args[1]["effective_session"] is fake_session

    # Assert the nested accumulation candidate builder received the exact
    # context object produced by the context builder.
    assert len(candidate_builder_calls) == 1
    candidate_builder_context = candidate_builder_calls[0]["execution_context"]
    assert candidate_builder_context is sentinel_context

    # Assert that the final state stores the exact context object from the builder
    assert state.signal_evidence_execution_context is sentinel_context
