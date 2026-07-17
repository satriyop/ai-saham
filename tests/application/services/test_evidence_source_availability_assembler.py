"""Tests for EvidenceSourceAvailabilityAssembler (ADR-041 CANONICAL-EVIDENCE-
BOUNDARY, formerly DQ-002 Blocker 2).

Covers the shadow-mode integration's required scenarios for the setup/flow
evidence groups it assembles: current data, future-dated (leaked) data,
missing data, lagged broker data, and the Bandar unassessed-contributor
guard. Availability is derived exclusively from `SetupProvenance`/
`FlowProvenance` — the exact consumed-row identities — never from raw
candle lists or a candidate object.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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
from src.domain.value_objects.canonical_signal_evidence_input import (
    BrokerDailyFlowRowIdentity,
    BrokerSummaryRowIdentity,
    CandleRowIdentity,
    FlowProvenance,
    SetupProvenance,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus

TICKER = "BBCA"


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


def _setup_provenance(*dates: date) -> SetupProvenance:
    return SetupProvenance(
        ticker=TICKER,
        candle_rows=tuple(
            CandleRowIdentity(ticker=TICKER, date=d, source="test") for d in dates
        ),
    )


def _flow_provenance(
    summary_dates: tuple[date, ...] = (),
    daily_flow_dates: tuple[date, ...] = (),
    has_bandar_contributor: bool = False,
) -> FlowProvenance:
    return FlowProvenance(
        ticker=TICKER,
        broker_summary_rows=tuple(
            BrokerSummaryRowIdentity(ticker=TICKER, date=d, source="test") for d in summary_dates
        ),
        broker_daily_flow_rows=tuple(
            BrokerDailyFlowRowIdentity(ticker=TICKER, date=d, broker_code="AK", source="test")
            for d in daily_flow_dates
        ),
        has_bandar_contributor=has_bandar_contributor,
    )


# --- setup group --------------------------------------------------------------


def test_current_candles_produce_current_status():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _setup_provenance(date(2026, 7, 15), date(2026, 7, 16), date(2026, 7, 17))

    setup = _assembler().assess_setup(effective_session=session, provenance=provenance)

    assert setup.evidence_group == "setup"
    assert setup.assessments[0].source_family == "candles"
    assert setup.assessments[0].status == SourceAvailabilityStatus.CURRENT
    assert setup.all_authoritative is True


def test_future_candle_date_cannot_become_authoritative():
    # A leaked future-dated candle in the provenance must still be caught.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _setup_provenance(date(2026, 7, 17), date(2026, 7, 20))

    setup = _assembler().assess_setup(effective_session=session, provenance=provenance)

    assert setup.assessments[0].status == SourceAvailabilityStatus.INVALID
    assert setup.assessments[0].is_authoritative is False
    assert setup.all_authoritative is False


def test_missing_candle_endpoint_produces_unknown():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _setup_provenance()

    setup = _assembler().assess_setup(effective_session=session, provenance=provenance)

    assert setup.assessments[0].status == SourceAvailabilityStatus.UNKNOWN
    assert setup.assessments[0].is_authoritative is False


# --- flow group ----------------------------------------------------------------


def test_current_broker_produces_current_status():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(summary_dates=(date(2026, 7, 17),))

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.CURRENT


def test_future_broker_date_is_excluded_and_cannot_become_authoritative():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(summary_dates=(date(2026, 7, 20),))

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.INVALID
    assert broker_summaries.is_authoritative is False


def test_lagged_broker_date_produces_late_within_settlement_lag():
    # Friday latest completed session; broker data one session behind
    # (Thursday) is within broker_summaries' configured 1-session lag.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(summary_dates=(date(2026, 7, 16),))

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.LATE
    assert broker_summaries.is_authoritative is False  # LATE is never authoritative


def test_broker_further_behind_produces_stale():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(summary_dates=(date(2026, 7, 13),))

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    broker_summaries = next(a for a in flow.assessments if a.source_family == "broker_summaries")
    assert broker_summaries.status == SourceAvailabilityStatus.STALE


def test_broker_daily_flow_current_when_its_own_consumed_date_is_tracked():
    # broker_daily_flow_rows can legitimately differ from broker_summary_rows
    # — its own max date is tracked separately in provenance.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(
        summary_dates=(date(2026, 7, 17),),
        daily_flow_dates=(date(2026, 7, 17),),
    )

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    daily_flow = next(a for a in flow.assessments if a.source_family == "broker_daily_flow")
    assert daily_flow.status == SourceAvailabilityStatus.CURRENT
    assert daily_flow.is_authoritative is True


def test_broker_daily_flow_is_unknown_when_consumed_date_not_tracked():
    # No broker_daily_flow_rows in provenance (e.g. no daily-flow row fell
    # inside the window) fails closed to UNKNOWN rather than inferring one
    # from broker_summary_rows.
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(summary_dates=(date(2026, 7, 17),))

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    daily_flow = next(a for a in flow.assessments if a.source_family == "broker_daily_flow")
    assert daily_flow.status == SourceAvailabilityStatus.UNKNOWN
    assert daily_flow.is_authoritative is False


def test_flow_group_not_authoritative_when_one_of_two_sources_is_unknown():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(summary_dates=(date(2026, 7, 17),))

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    assert flow.all_authoritative is False


def test_missing_provenance_falls_back_to_unknown_not_a_crash():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance()

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    assert all(a.status == SourceAvailabilityStatus.UNKNOWN for a in flow.assessments)


# --- Bandar unassessed-contributor guard -----------------------------------------


def test_bandar_present_marks_flow_group_as_having_an_unassessed_contributor():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(
        summary_dates=(date(2026, 7, 17),),
        daily_flow_dates=(date(2026, 7, 17),),
        has_bandar_contributor=True,
    )

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    assert all(a.status == SourceAvailabilityStatus.CURRENT for a in flow.assessments)
    assert all(a.is_authoritative for a in flow.assessments)
    assert flow.unassessed_contributors == ("bandar_detector",)
    assert flow.all_authoritative is False


def test_bandar_absent_does_not_count_as_an_unassessed_contributor():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    provenance = _flow_provenance(
        summary_dates=(date(2026, 7, 17),),
        daily_flow_dates=(date(2026, 7, 17),),
        has_bandar_contributor=False,
    )

    flow = _assembler().assess_flow(effective_session=session, provenance=provenance)

    assert flow.unassessed_contributors == ()
    assert flow.all_authoritative is True


# --- determinism -----------------------------------------------------------------


def test_identical_inputs_produce_identical_availability_output():
    session = _session(date(2026, 7, 17), _wib(2026, 7, 17))
    setup_provenance = _setup_provenance(date(2026, 7, 17))
    flow_provenance = _flow_provenance(summary_dates=(date(2026, 7, 16),))
    assembler = _assembler()

    first_setup = assembler.assess_setup(effective_session=session, provenance=setup_provenance)
    second_setup = assembler.assess_setup(effective_session=session, provenance=setup_provenance)
    assert first_setup == second_setup

    first_flow = assembler.assess_flow(effective_session=session, provenance=flow_provenance)
    second_flow = assembler.assess_flow(effective_session=session, provenance=flow_provenance)
    assert first_flow == second_flow
