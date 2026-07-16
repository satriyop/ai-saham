"""Unit tests for freshness computation from EffectiveMarketSession (DQ-002B).

No test here depends on weekday/wall-clock arithmetic — that behavior is
owned and tested by EffectiveMarketSessionResolver
(test_effective_market_session_resolver.py). These tests only prove
compute_data_freshness's own derivation from an already-resolved
EffectiveMarketSession.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.application.services.data_freshness_service import compute_data_freshness
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.value_objects.data_freshness_status import (
    SourceAlignmentState,
    SourceFreshnessState,
)

_WIB = ZoneInfo("Asia/Jakarta")
_FIXED_NOW = datetime(2026, 7, 14, 9, 26, tzinfo=_WIB)


def _session(
    *,
    latest_completed_session: date | None,
    is_eod_pending: bool,
) -> EffectiveMarketSession:
    return EffectiveMarketSession(
        run_at=_FIXED_NOW,
        decision_at=_FIXED_NOW,
        latest_completed_session=latest_completed_session,
        analysis_as_of=latest_completed_session,
        market_session_name="REGULAR",
        is_eod_pending=is_eod_pending,
        resolution_source="test_fixture",
        notes=(),
    )


def test_same_candle_and_broker_date_is_aligned():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.alignment_state is SourceAlignmentState.ALIGNED
    assert result.sources_aligned is True


def test_different_candle_and_broker_dates_are_lag():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 10),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.alignment_state is SourceAlignmentState.LAG
    assert result.sources_aligned is False


def test_missing_candle_date_is_missing_and_not_aligned():
    result = compute_data_freshness(
        candle_as_of=None,
        broker_as_of=date(2026, 7, 13),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.candle_state is SourceFreshnessState.MISSING
    assert result.alignment_state is SourceAlignmentState.MISSING
    assert result.sources_aligned is False


def test_missing_broker_date_is_missing_and_not_aligned():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=None,
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.broker_state is SourceFreshnessState.MISSING
    assert result.alignment_state is SourceAlignmentState.MISSING
    assert result.sources_aligned is False


def test_prior_session_data_during_pre_close_session_is_pending_eod_when_eod_pending():
    # Regression for the audit bug: prior-day EOD during a live pre-close
    # session is correct and current, but must read PENDING_EOD, never
    # STALE, and never the retired "OK" state.
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.expected_latest_eod == date(2026, 7, 13)
    assert result.candle_state is SourceFreshnessState.PENDING_EOD
    assert result.broker_state is SourceFreshnessState.PENDING_EOD
    assert result.candle_state.value != "OK"
    assert result.broker_state.value != "OK"


def test_same_source_dates_after_close_are_ready_when_eod_pending_is_false():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 14),
        broker_as_of=date(2026, 7, 14),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 14), is_eod_pending=False
        ),
    )
    assert result.expected_latest_eod == date(2026, 7, 14)
    assert result.candle_state is SourceFreshnessState.READY
    assert result.broker_state is SourceFreshnessState.READY


def test_stale_source_dates_remain_stale_regardless_of_eod_pending():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 10),
        broker_as_of=date(2026, 7, 10),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.candle_state is SourceFreshnessState.STALE
    assert result.broker_state is SourceFreshnessState.STALE


def test_no_expected_latest_eod_produces_unknown_for_present_source_dates():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        effective_session=_session(latest_completed_session=None, is_eod_pending=False),
    )
    assert result.candle_state is SourceFreshnessState.UNKNOWN
    assert result.broker_state is SourceFreshnessState.UNKNOWN


def test_signal_evidence_coverage_passes_through_without_approximation():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
        signal_evidence_coverage=0.4,
    )
    assert result.signal_evidence_coverage == 0.4


def test_signal_evidence_coverage_is_explicit_none_when_unavailable():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        effective_session=_session(
            latest_completed_session=date(2026, 7, 13), is_eod_pending=True
        ),
    )
    assert result.signal_evidence_coverage is None
