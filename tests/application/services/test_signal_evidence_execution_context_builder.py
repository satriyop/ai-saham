from datetime import date, datetime
import pytest
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)


def _session(day: date) -> EffectiveMarketSession:
    return EffectiveMarketSession(
        run_at=datetime.combine(day, MARKET_CLOSE, tzinfo=IDX_TIMEZONE),
        decision_at=datetime.combine(day, MARKET_CLOSE, tzinfo=IDX_TIMEZONE),
        latest_completed_session=day,
        analysis_as_of=day,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test",
    )


def test_builder_returns_exact_supplied_session():
    session = _session(date(2026, 7, 17))
    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=None)
    result = builder.build(
        effective_session=session,
        coverage_start=date(2026, 7, 10),
        coverage_end=date(2026, 7, 17),
    )
    assert result.effective_session is session


def test_calendar_loader_called_once_and_creates_availability():
    session = _session(date(2026, 7, 17))
    calls = []

    def loader(start, end):
        calls.append((start, end))
        return KnownTradingSessionCalendar(
            sessions=(date(2026, 7, 10), date(2026, 7, 17)),
            coverage_start=start,
            coverage_end=end,
        )

    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=loader)
    result = builder.build(
        effective_session=session,
        coverage_start=date(2026, 7, 10),
        coverage_end=date(2026, 7, 17),
    )

    assert len(calls) == 1
    assert calls[0] == (date(2026, 7, 10), date(2026, 7, 17))
    assert result.source_availability_use_case is not None


def test_missing_loader_produces_none_availability():
    session = _session(date(2026, 7, 17))
    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=None)
    result = builder.build(
        effective_session=session,
        coverage_start=date(2026, 7, 10),
        coverage_end=date(2026, 7, 17),
    )
    assert result.source_availability_use_case is None


def test_loader_returning_none_produces_none_availability():
    session = _session(date(2026, 7, 17))
    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=lambda s, e: None)
    result = builder.build(
        effective_session=session,
        coverage_start=date(2026, 7, 10),
        coverage_end=date(2026, 7, 17),
    )
    assert result.source_availability_use_case is None


def test_loader_exception_produces_unavailable_assessor():
    session = _session(date(2026, 7, 17))

    def loader(s, e):
        raise RuntimeError("DB connection timeout")

    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=loader)
    result = builder.build(
        effective_session=session,
        coverage_start=date(2026, 7, 10),
        coverage_end=date(2026, 7, 17),
    )
    # Operational exception produces an assessor that fails closed to UNKNOWN
    # without propagating the RuntimeError.
    assert result.source_availability_use_case is None

    from src.domain.value_objects.canonical_signal_evidence_input import SetupProvenance
    provenance = SetupProvenance(ticker="BBRI", candle_rows=())
    setup = EvidenceSourceAvailabilityAssembler(result.source_availability_use_case).assess_setup(
        effective_session=session,
        provenance=provenance,
    )
    assert setup.assessments[0].status == SourceAvailabilityStatus.UNKNOWN


def test_value_error_from_loader_propagates():
    session = _session(date(2026, 7, 17))

    def loader(s, e):
        raise ValueError("Invalid session range")

    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=loader)
    with pytest.raises(ValueError, match="Invalid session range"):
        builder.build(
            effective_session=session,
            coverage_start=date(2026, 7, 10),
            coverage_end=date(2026, 7, 17),
        )


def test_type_error_from_loader_propagates():
    session = _session(date(2026, 7, 17))

    def loader(s, e):
        raise TypeError("Invalid types")

    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=loader)
    with pytest.raises(TypeError, match="Invalid types"):
        builder.build(
            effective_session=session,
            coverage_start=date(2026, 7, 10),
            coverage_end=date(2026, 7, 17),
        )


def test_invalid_coverage_bounds_raises_value_error_without_calling_loader():
    session = _session(date(2026, 7, 17))
    calls = []

    def loader(s, e):
        calls.append((s, e))
        return None

    builder = SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=loader)
    with pytest.raises(ValueError, match="coverage_start cannot be after coverage_end"):
        builder.build(
            effective_session=session,
            coverage_start=date(2026, 7, 17),
            coverage_end=date(2026, 7, 10),
        )
    assert not calls
