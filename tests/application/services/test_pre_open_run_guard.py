"""Tests for pre-open workflow run-guard policy."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.application.services.pre_open_run_guard import (
    PreOpenCaptureStartKind,
    build_pre_open_run_guard,
    evaluate_pre_open_capture_window,
)
from src.domain.value_objects.market_status import MarketStatus


def _stockbit_status(
    session_name: str, is_open: bool, is_pre_open: bool, dt: datetime
) -> MarketStatus:
    status = MarketStatus(
        status="STATUS_OPEN" if is_open else "STATUS_CLOSE",
        session_name=session_name,
        is_open=is_open,
        session_open=None,
        session_close=None,
        fetched_at=dt,
        source="stockbit",
    )
    assert status.is_pre_open == is_pre_open
    return status


def _local_clock_status(session_name: str, is_open: bool, dt: datetime) -> MarketStatus:
    return MarketStatus(
        status="STATUS_OPEN" if is_open else "STATUS_CLOSE",
        session_name=session_name,
        is_open=is_open,
        session_open=None,
        session_close=None,
        fetched_at=dt,
        source="local_clock",
    )


def test_stockbit_closed_non_preopen_blocks_without_override():
    dt = datetime(2026, 6, 12, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Weekend", False, False, dt),
        allow_non_trading_day=False,
    )

    assert guard.error is not None
    assert "non-trading day" in guard.error


def test_stockbit_allow_non_trading_day_returns_warning_not_error():
    dt = datetime(2026, 6, 12, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Weekend", False, False, dt),
        allow_non_trading_day=True,
    )

    assert guard.error is None
    assert guard.is_trading_day is False
    assert any("non-trading day" in warning for warning in guard.warnings)


def test_fallback_wall_clock_weekend_blocks_unless_allowed():
    dt = datetime(2026, 6, 13, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_local_clock_status("Weekend", False, dt),
        allow_non_trading_day=False,
    )

    assert guard.error is not None
    assert "weekend" in guard.error


def test_fallback_wall_clock_weekend_allowed_returns_warning():
    dt = datetime(2026, 6, 13, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_local_clock_status("Weekend", False, dt),
        allow_non_trading_day=True,
    )

    assert guard.error is None
    assert guard.is_trading_day is False
    assert any("weekend" in warning for warning in guard.warnings)


def test_outside_pre_open_time_adds_timing_warning():
    dt = datetime(2026, 6, 12, 10, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_local_clock_status("Regular", True, dt),
        allow_non_trading_day=False,
    )

    assert guard.error is None
    assert any("outside IDX pre-open window" in warning for warning in guard.warnings)
    assert guard.outside_window is True


def test_valid_pre_open_time_has_no_timing_warning():
    dt = datetime(2026, 6, 12, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Pre-Open", False, True, dt),
        allow_non_trading_day=False,
    )

    assert guard.error is None
    assert guard.is_trading_day is True
    assert not any("outside IDX pre-open window" in warning for warning in guard.warnings)
    assert guard.outside_window is False


def test_stockbit_post_market_during_ncp_lock_is_not_a_non_trading_day():
    """NCP lock closes FCA; Stockbit reports Post-Market at 08:57 on a trading day."""
    dt = datetime(2026, 8, 25, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Post-Market", False, False, dt),
        allow_non_trading_day=False,
        same_day_auction_evidence=True,
    )

    assert guard.error is None
    assert guard.is_trading_day is True
    assert any("NCP lock" in warning for warning in guard.warnings)
    assert guard.outside_window is False


def test_stockbit_post_market_without_auction_evidence_is_non_trading_day():
    """Weekday holiday: Stockbit still reports Post-Market, never Weekend."""
    dt = datetime(2026, 6, 11, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Post-Market", False, False, dt),
        allow_non_trading_day=False,
        same_day_auction_evidence=False,
    )

    assert guard.error is not None
    assert "non-trading day" in guard.error
    assert guard.is_trading_day is False


def test_stockbit_post_market_holiday_allow_override_returns_warning():
    dt = datetime(2026, 6, 11, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Post-Market", False, False, dt),
        allow_non_trading_day=True,
        same_day_auction_evidence=False,
    )

    assert guard.error is None
    assert guard.is_trading_day is False
    assert any("non-trading day" in warning for warning in guard.warnings)


def test_stockbit_post_market_after_hours_is_non_trading_day_even_with_iev():
    dt = datetime(2026, 8, 25, 16, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Post-Market", False, False, dt),
        allow_non_trading_day=False,
        same_day_auction_evidence=True,
    )

    assert guard.error is not None
    assert "non-trading day" in guard.error
    assert guard.is_trading_day is False
    assert guard.outside_window is True


def test_stockbit_post_market_on_weekend_blocks_without_weekend_session_name():
    dt = datetime(2026, 6, 13, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Post-Market", False, False, dt),
        allow_non_trading_day=False,
        same_day_auction_evidence=False,
    )

    assert guard.error is not None
    assert guard.is_trading_day is False


def test_stockbit_opening_call_auction_during_pre_open_is_trading_day():
    dt = datetime(2026, 8, 25, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Opening Call Auction", False, True, dt),
        allow_non_trading_day=False,
    )

    assert guard.error is None
    assert guard.is_trading_day is True
    assert guard.outside_window is False


def _capture_at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 9, hour, minute, second, tzinfo=ZoneInfo("Asia/Jakarta"))


def test_capture_window_accepts_ncp_lock_start_inclusive():
    window = evaluate_pre_open_capture_window(_capture_at(8, 56))
    assert window.kind is PreOpenCaptureStartKind.IN_LOCK_WINDOW
    assert window.rejection is None
    assert window.in_lock_window is True


def test_capture_window_accepts_last_second_before_matching():
    window = evaluate_pre_open_capture_window(_capture_at(8, 57, 59))
    assert window.kind is PreOpenCaptureStartKind.IN_LOCK_WINDOW
    assert window.rejection is None


def test_capture_window_matching_start_is_late_wake_before_any_lock():
    window = evaluate_pre_open_capture_window(_capture_at(8, 58))
    assert window.kind is PreOpenCaptureStartKind.LATE_WAKE
    assert window.late_wake is True
    assert window.rejection is not None
    assert "late wake" in window.rejection
    assert "No lock is claimed" in window.rejection
    assert "08:56" in window.rejection and "08:58" in window.rejection


def test_capture_window_post_open_start_is_late_wake():
    window = evaluate_pre_open_capture_window(_capture_at(9, 7))
    assert window.kind is PreOpenCaptureStartKind.LATE_WAKE
    assert "09:07:00" in (window.rejection or "")
    assert "No lock is claimed" in (window.rejection or "")
    assert "allow-non-trading-day" not in (window.rejection or "")


def test_capture_window_converts_utc_to_jakarta_before_classifying():
    utc_after_lock = datetime(2026, 9, 9, 2, 7, tzinfo=timezone.utc)  # 09:07 WIB
    window = evaluate_pre_open_capture_window(utc_after_lock)
    assert window.kind is PreOpenCaptureStartKind.LATE_WAKE

    utc_in_lock = datetime(2026, 9, 9, 1, 56, tzinfo=timezone.utc)  # 08:56 WIB
    assert (
        evaluate_pre_open_capture_window(utc_in_lock).kind is PreOpenCaptureStartKind.IN_LOCK_WINDOW
    )


def test_capture_window_too_early_does_not_claim_lock():
    window = evaluate_pre_open_capture_window(_capture_at(8, 50))
    assert window.kind is PreOpenCaptureStartKind.TOO_EARLY
    assert window.rejection is not None
    assert "No lock is claimed" in window.rejection
    assert "late wake" not in window.rejection
