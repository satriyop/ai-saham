"""Tests for accumulation capture session fail-closed classification."""

from datetime import date

from src.application.services.accum_session_capture_outcome import (
    AccumSessionCaptureStatus,
    classify_accum_session_capture,
    missing_ihsg_sessions,
)

SESSION = date(2026, 8, 25)
HOLE = date(2026, 8, 20)


def test_processed_session_is_captured() -> None:
    outcome = classify_accum_session_capture(
        session=SESSION,
        processed_dates=(SESSION,),
        ihsg_has_session=True,
        same_day_auction_evidence=True,
    )
    assert outcome.ok is True
    assert outcome.status is AccumSessionCaptureStatus.CAPTURED


def test_ihsg_present_but_unprocessed_is_a_hole() -> None:
    outcome = classify_accum_session_capture(
        session=HOLE,
        processed_dates=(),
        ihsg_has_session=True,
        same_day_auction_evidence=False,
    )
    assert outcome.ok is False
    assert outcome.status is AccumSessionCaptureStatus.EMPTY_ON_TRADING_SESSION


def test_iev_without_ihsg_is_eod_lag() -> None:
    outcome = classify_accum_session_capture(
        session=SESSION,
        processed_dates=(),
        ihsg_has_session=False,
        same_day_auction_evidence=True,
    )
    assert outcome.ok is False
    assert outcome.status is AccumSessionCaptureStatus.EOD_DATA_MISSING


def test_no_ihsg_no_iev_is_holiday_success() -> None:
    outcome = classify_accum_session_capture(
        session=date(2026, 8, 17),
        processed_dates=(),
        ihsg_has_session=False,
        same_day_auction_evidence=False,
    )
    assert outcome.ok is True
    assert outcome.status is AccumSessionCaptureStatus.HOLIDAY


def test_missing_ihsg_sessions_skips_already_captured() -> None:
    missing = missing_ihsg_sessions(
        ihsg_dates=(date(2026, 8, 19), HOLE, date(2026, 8, 21)),
        captured_sessions=(date(2026, 8, 19), date(2026, 8, 21)),
    )
    assert missing == (HOLE,)


def test_missing_ihsg_sessions_empty_when_whole() -> None:
    dates = (date(2026, 8, 19), date(2026, 8, 21))
    assert missing_ihsg_sessions(ihsg_dates=dates, captured_sessions=dates) == ()
