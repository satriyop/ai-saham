"""
Market-calendar-aware freshness computation.

Computes a `DataFreshnessStatus` for a ticker's candle/broker source dates
against the expected latest IDX end-of-day session, derived from local
wall-clock time and weekday arithmetic only. No network or calendar-provider
calls — see `src/domain/value_objects/trading_calendar.py` for the documented
weekend-only limitation (public holidays are not modeled; the direction of
any resulting lag is always correct).

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from src.domain.value_objects.data_freshness_status import (
    DataFreshnessStatus,
    SourceAlignmentState,
    SourceFreshnessState,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.trading_calendar import last_weekday


def _expected_latest_eod(screen_date: date, now: datetime | None) -> tuple[date | None, bool]:
    """Resolve the most recent IDX session for which EOD data should already
    exist, plus whether that expectation is still "pending" (i.e. the
    session covering `screen_date` is open or hasn't closed yet).

    Returns (expected_latest_eod, eod_pending). `eod_pending` is True only
    when `screen_date` is today's live trading day and the regular session
    has not yet reached market close — the scenario where prior-session data
    is the best available and must read PENDING_EOD, not STALE.
    """
    if now is None:
        now = datetime.now(IDX_TIMEZONE)
    now_wib = now.astimezone(IDX_TIMEZONE)
    today_wib = now_wib.date()

    if screen_date > today_wib:
        return None, False  # future date: cannot determine expectation

    if screen_date < today_wib:
        # Already-elapsed calendar date: its session (if any) is long closed.
        return last_weekday(screen_date), False

    # screen_date == today_wib (live).
    if screen_date.weekday() >= 5:
        return last_weekday(screen_date - timedelta(days=1)), False

    if now_wib.time() >= MARKET_CLOSE:
        return screen_date, False

    return last_weekday(screen_date - timedelta(days=1)), True


def _classify_source_state(
    source_date: date | None,
    expected_latest_eod: date | None,
    eod_pending: bool,
) -> SourceFreshnessState:
    if source_date is None:
        return SourceFreshnessState.MISSING
    if expected_latest_eod is None:
        return SourceFreshnessState.UNKNOWN
    if source_date == expected_latest_eod:
        return SourceFreshnessState.PENDING_EOD if eod_pending else SourceFreshnessState.READY
    if source_date < expected_latest_eod:
        return SourceFreshnessState.STALE
    return SourceFreshnessState.READY  # newer than expected (clock skew) — at least current


def _classify_alignment(
    candle_as_of: date | None, broker_as_of: date | None
) -> SourceAlignmentState:
    if candle_as_of is None or broker_as_of is None:
        return SourceAlignmentState.MISSING
    if candle_as_of == broker_as_of:
        return SourceAlignmentState.ALIGNED
    return SourceAlignmentState.LAG


def compute_data_freshness(
    *,
    candle_as_of: date | None,
    broker_as_of: date | None,
    screen_date: date,
    now: datetime | None = None,
    signal_evidence_coverage: float | None = None,
) -> DataFreshnessStatus:
    """Compute typed freshness/alignment for one ticker's candle+broker data.

    `screen_date` is the effective "as of" date for the run (e.g. a screen's
    `screened_at` or a deterministic replay date), not necessarily today.
    `now` is injectable for tests; defaults to the current Asia/Jakarta time.
    """
    expected_latest_eod, eod_pending = _expected_latest_eod(screen_date, now)

    return DataFreshnessStatus(
        candle_as_of=candle_as_of,
        broker_as_of=broker_as_of,
        expected_latest_eod=expected_latest_eod,
        candle_state=_classify_source_state(candle_as_of, expected_latest_eod, eod_pending),
        broker_state=_classify_source_state(broker_as_of, expected_latest_eod, eod_pending),
        alignment_state=_classify_alignment(candle_as_of, broker_as_of),
        sources_aligned=(
            candle_as_of is not None
            and broker_as_of is not None
            and candle_as_of == broker_as_of
        ),
        signal_evidence_coverage=signal_evidence_coverage,
    )
