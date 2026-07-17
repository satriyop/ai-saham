"""Tests for EvidenceSourceAvailabilityAssembler — DQ-002 Blocker 2.

Covers the shadow-mode integration's required scenarios for the setup/flow
evidence groups it assembles: current data, future-dated (leaked) data,
missing data, lagged broker data, and the Bandar unassessed-contributor
guard. Setup availability is derived from the literal `candles` list passed
in (the same list handed to the evidence builder), never from a separately
fetched candidate field.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus


def _wib(y, m, d, hh=20, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IDX_TIMEZONE)


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _calendar() -> KnownTradingSessionCalendar:
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    return KnownTradingSessionCalendar(
        sessions=_weekdays(start, end), coverage_start=start, coverage_end=end
    )


def _session(latest_completed_session: date, decision_at: datetime) -> EffectiveMarketSession:
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=latest_completed_session,
        analysis_as_of=latest_completed_session,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _assembler() -> EvidenceSourceAvailabilityAssembler:
    return EvidenceSourceAvailabilityAssembler(
        AssessSourceAvailabilityUseCase(calendar=_calendar())
    )


def _candles(*dates: date) -> list[SimpleNamespace]:
    return [SimpleNamespace(date=d) for d in dates]


def _candidate(
    latest_broker_date: date | None = None,
    latest_broker_daily_flow_date: date | None = None,
    bandar_detector: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        latest_broker_date=latest_broker_date,
        latest_broker_daily_flow_date=latest_broker_daily_flow_date,
        bandar_detector=bandar_detector,
    )


# --- setup group ------------------------------------------------------------


def test_current_candles_produce_current_status():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candles = _candles(date(2026, 7, 15), date(2026, 7, 16), date(2026, 7, 17))

    setup = _assembler().assess_setup(effective_session=session, candles=candles)

    assert setup.evidence_group == "setup"
    assert setup.assessments[0].source_family == "candles"
    assert setup.assessments[0].status == SourceAvailabilityStatus.CURRENT
    assert setup.all_authoritative is True


def test_future_candle_date_cannot_become_authoritative():
    # A leaked future-dated candle in the actually-consumed list must still
    # be caught.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candles = _candles(date(2026, 7, 17), date(2026, 7, 20))

    setup = _assembler().assess_setup(effective_session=session, candles=candles)

    assert setup.assessments[0].status == SourceAvailabilityStatus.INVALID
    assert setup.assessments[0].is_authoritative is False
    assert setup.all_authoritative is False


def test_missing_candle_endpoint_produces_unknown():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))

    setup = _assembler().assess_setup(effective_session=session, candles=())

    assert setup.assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert setup.assessments[0].is_authoritative is False


# --- flow group --------------------------------------------------------------


def test_current_broker_produces_current_status():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 17))

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.CURRENT


def test_future_broker_date_is_excluded_and_cannot_become_authoritative():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 20))

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.INVALID
    assert broker_summaries.is_authoritative is False


def test_lagged_broker_date_produces_late_within_settlement_lag():
    # Friday latest completed session; broker data one session behind
    # (Thursday) is within broker_summaries' configured 1-session lag.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 16))

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.LATE
    assert broker_summaries.is_authoritative is False  # LATE is never authoritative


def test_broker_further_behind_produces_stale():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 13))

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.STALE


def test_broker_daily_flow_current_when_its_own_consumed_date_is_tracked():
    # latest_broker_daily_flow_date is tracked separately from
    # latest_broker_date (AccumulationCandidateEvaluator: daily_flows rows
    # are a subset of the broker_summaries window, so its own max date can
    # legitimately differ, e.g. when the latest window date has no matching
    # daily-flow row).
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(
        latest_broker_date=date(2026, 7, 17),
        latest_broker_daily_flow_date=date(2026, 7, 17),
    )

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    daily_flow = next(a for a in flow.assessments if a.source_family == "broker_daily_flow")
    assert daily_flow.status == SourceAvailabilityStatus.CURRENT
    assert daily_flow.is_authoritative is True


def test_broker_daily_flow_is_unknown_when_consumed_date_not_tracked():
    # A candidate that never populated latest_broker_daily_flow_date (e.g.
    # no daily-flow row fell inside the broker_summaries window) must fail
    # closed to UNKNOWN rather than reuse latest_broker_date as an inferred
    # timestamp for a distinct source family.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 17))

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    daily_flow = next(a for a in flow.assessments if a.source_family == "broker_daily_flow")
    assert daily_flow.status == SourceAvailabilityStatus.UNKNOWN
    assert daily_flow.is_authoritative is False


def test_flow_group_not_authoritative_when_one_of_two_sources_is_unknown():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 17))

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    assert flow.all_authoritative is False


def test_candidate_missing_attributes_falls_back_to_unknown_not_a_crash():
    # A caller-supplied candidate object without latest_broker_date/
    # latest_broker_daily_flow_date/bandar_detector attributes (e.g. a
    # dict-shaped test fake) must not raise — getattr must default to None,
    # which the use case maps to UNKNOWN, never an inferred timestamp.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = {"ticker": "BBCA"}

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    assert all(a.status == SourceAvailabilityStatus.UNKNOWN for a in flow.assessments)
    assert flow.unassessed_contributors == ()


# --- Bandar unassessed-contributor guard -------------------------------------


def test_bandar_present_marks_flow_group_as_having_an_unassessed_contributor():
    # candidate.bandar_detector is a real, currently-consumed contributor to
    # FlowConfirmationEvidence sourced from a live Stockbit scrape, not a
    # registered SQLite source family — it must never let all_authoritative
    # report True just because broker_summaries/broker_daily_flow are.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(
        latest_broker_date=date(2026, 7, 17),
        latest_broker_daily_flow_date=date(2026, 7, 17),
        bandar_detector=SimpleNamespace(broad_score=5),
    )

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    # Both listed sources are CURRENT/authoritative...
    assert all(a.status == SourceAvailabilityStatus.CURRENT for a in flow.assessments)
    assert all(a.is_authoritative for a in flow.assessments)
    # ...yet the group as a whole must not claim full authority.
    assert flow.unassessed_contributors == ("bandar_detector",)
    assert flow.all_authoritative is False


def test_bandar_absent_does_not_count_as_an_unassessed_contributor():
    # When bandar_detector was never fetched (None), it did not contribute
    # to this decision's FlowConfirmationEvidence, so it must not be listed.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candidate = _candidate(
        latest_broker_date=date(2026, 7, 17),
        latest_broker_daily_flow_date=date(2026, 7, 17),
        bandar_detector=None,
    )

    flow = _assembler().assess_flow(effective_session=session, candidate=candidate)

    assert flow.unassessed_contributors == ()
    assert flow.all_authoritative is True


# --- determinism --------------------------------------------------------------


def test_identical_inputs_produce_identical_availability_output():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    candles = _candles(date(2026, 7, 17))
    candidate = _candidate(latest_broker_date=date(2026, 7, 16))
    assembler = _assembler()

    first_setup = assembler.assess_setup(effective_session=session, candles=candles)
    second_setup = assembler.assess_setup(effective_session=session, candles=candles)
    assert first_setup == second_setup

    first_flow = assembler.assess_flow(effective_session=session, candidate=candidate)
    second_flow = assembler.assess_flow(effective_session=session, candidate=candidate)
    assert first_flow == second_flow
