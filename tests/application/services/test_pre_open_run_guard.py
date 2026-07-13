"""Tests for pre-open workflow run-guard policy."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.application.services.pre_open_run_guard import build_pre_open_run_guard
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


def test_valid_pre_open_time_has_no_timing_warning():
    dt = datetime(2026, 6, 12, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = build_pre_open_run_guard(
        run_at=dt,
        market_status=_stockbit_status("Pre-Open", False, True, dt),
        allow_non_trading_day=False,
    )

    assert guard.error is None
    assert not any("outside IDX pre-open window" in warning for warning in guard.warnings)
