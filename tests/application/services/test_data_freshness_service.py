"""Unit tests for the market-calendar-aware freshness service (S3)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.application.services.data_freshness_service import compute_data_freshness
from src.domain.value_objects.data_freshness_status import (
    SourceAlignmentState,
    SourceFreshnessState,
)

_WIB = ZoneInfo("Asia/Jakarta")

# Tuesday 2026-07-14, 09:26 WIB — regular session open, before market close.
_OPEN_SESSION_NOW = datetime(2026, 7, 14, 9, 26, tzinfo=_WIB)
# Same trading day, 16:30 WIB — after market close, EOD expected.
_AFTER_CLOSE_NOW = datetime(2026, 7, 14, 16, 30, tzinfo=_WIB)


def test_same_candle_and_broker_date_is_aligned():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.alignment_state is SourceAlignmentState.ALIGNED
    assert result.sources_aligned is True


def test_different_candle_and_broker_dates_are_lag():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 10),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.alignment_state is SourceAlignmentState.LAG
    assert result.sources_aligned is False


def test_missing_candle_date_is_missing_and_not_aligned():
    result = compute_data_freshness(
        candle_as_of=None,
        broker_as_of=date(2026, 7, 13),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.candle_state is SourceFreshnessState.MISSING
    assert result.alignment_state is SourceAlignmentState.MISSING
    assert result.sources_aligned is False


def test_missing_broker_date_is_missing_and_not_aligned():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=None,
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.broker_state is SourceFreshnessState.MISSING
    assert result.alignment_state is SourceAlignmentState.MISSING
    assert result.sources_aligned is False


def test_prior_session_data_during_open_market_is_pending_eod_not_stale():
    # Regression for the audit bug: 09:26 WIB, prior-day EOD is correct and
    # current, but the old code showed it as bare "OK" — it must now be
    # PENDING_EOD, never STALE, and never the retired "OK" state.
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.expected_latest_eod == date(2026, 7, 13)
    assert result.candle_state is SourceFreshnessState.PENDING_EOD
    assert result.broker_state is SourceFreshnessState.PENDING_EOD
    assert result.candle_state.value != "OK"
    assert result.broker_state.value != "OK"


def test_older_than_previous_session_date_is_stale():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 10),
        broker_as_of=date(2026, 7, 10),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.candle_state is SourceFreshnessState.STALE
    assert result.broker_state is SourceFreshnessState.STALE


def test_current_day_data_after_market_close_is_ready():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 14),
        broker_as_of=date(2026, 7, 14),
        screen_date=date(2026, 7, 14),
        now=_AFTER_CLOSE_NOW,
    )
    assert result.expected_latest_eod == date(2026, 7, 14)
    assert result.candle_state is SourceFreshnessState.READY
    assert result.broker_state is SourceFreshnessState.READY


def test_weekend_date_uses_previous_trading_session_as_expected_latest_eod():
    # Saturday 2026-07-18: no session; expected latest EOD rolls back to
    # Friday 2026-07-17 regardless of time of day.
    saturday_now = datetime(2026, 7, 18, 11, 0, tzinfo=_WIB)
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 17),
        broker_as_of=date(2026, 7, 17),
        screen_date=date(2026, 7, 18),
        now=saturday_now,
    )
    assert result.expected_latest_eod == date(2026, 7, 17)
    assert result.candle_state is SourceFreshnessState.READY


def test_signal_evidence_coverage_passes_through_without_approximation():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
        signal_evidence_coverage=0.4,
    )
    assert result.signal_evidence_coverage == 0.4


def test_signal_evidence_coverage_is_explicit_none_when_unavailable():
    result = compute_data_freshness(
        candle_as_of=date(2026, 7, 13),
        broker_as_of=date(2026, 7, 13),
        screen_date=date(2026, 7, 14),
        now=_OPEN_SESSION_NOW,
    )
    assert result.signal_evidence_coverage is None
