"""Classify one accumulation capture session as success, holiday, or failure.

Nightly cron used to emit COMPLETION_OK when capture processed zero dates:
IHSG candles unpublished (EOD lag) and a missed prior session look the same
as an IDX holiday. Continuity only alarms later, and a fail-closed wrapper
that treats empty capture as success is just a quiet hole.

This module is the application policy for that distinction. Adapters supply
the evidence (local IHSG candle, same-day IEV rows, already-captured
sessions) and map the outcome to an exit code. No I/O lives here.

Layer: Application
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum


class AccumSessionCaptureStatus(str, Enum):
    """Outcome of one requested economic session."""

    CAPTURED = "captured"
    HOLIDAY = "holiday"
    EOD_DATA_MISSING = "eod_data_missing"
    EMPTY_ON_TRADING_SESSION = "empty_on_trading_session"


@dataclass(frozen=True)
class AccumSessionCaptureOutcome:
    status: AccumSessionCaptureStatus
    ok: bool
    reason: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "reason": self.reason,
        }


def classify_accum_session_capture(
    *,
    session: date,
    processed_dates: Iterable[date],
    ihsg_has_session: bool,
    same_day_auction_evidence: bool,
) -> AccumSessionCaptureOutcome:
    """Decide whether a single-session capture may report success.

    Rules, in order:

    1. Session is in ``processed_dates`` → captured (idempotent reruns included).
    2. Local IHSG has that session's candle → it was a trading day; empty
       capture is a hole (``EMPTY_ON_TRADING_SESSION``).
    3. No IHSG candle, but same-day auction evidence (IEV rows) → the market
       traded and EOD candles have not landed (``EOD_DATA_MISSING``).
    4. Otherwise → treat as a non-session (holiday / weekend) (``HOLIDAY``).

    Same-day auction evidence is the pre-open IEV snapshot, which exists only
    when the board actually opened. It is not calendar authority and must not
    be used as a trading-date axis for capture itself.
    """
    processed = frozenset(processed_dates)
    if session in processed:
        return AccumSessionCaptureOutcome(
            status=AccumSessionCaptureStatus.CAPTURED,
            ok=True,
            reason=f"{session.isoformat()} processed",
        )
    if ihsg_has_session:
        return AccumSessionCaptureOutcome(
            status=AccumSessionCaptureStatus.EMPTY_ON_TRADING_SESSION,
            ok=False,
            reason=(
                f"{session.isoformat()} has a local IHSG candle but capture processed no dates"
            ),
        )
    if same_day_auction_evidence:
        return AccumSessionCaptureOutcome(
            status=AccumSessionCaptureStatus.EOD_DATA_MISSING,
            ok=False,
            reason=(
                f"{session.isoformat()} has same-day IEV rows but no local "
                "IHSG candle; EOD data is not yet available"
            ),
        )
    return AccumSessionCaptureOutcome(
        status=AccumSessionCaptureStatus.HOLIDAY,
        ok=True,
        reason=(
            f"{session.isoformat()} has no IHSG candle and no same-day IEV "
            "rows; treating as a non-trading session"
        ),
    )


def missing_ihsg_sessions(
    *,
    ihsg_dates: Iterable[date],
    captured_sessions: Iterable[date],
) -> tuple[date, ...]:
    """IHSG trading dates in ``ihsg_dates`` with no captured observation session.

    Catch-up only fills true holes (zero observations). Dates that already
    have rows for any accum cohort are left unchanged — do not rewrite.
    """
    captured = frozenset(captured_sessions)
    return tuple(day for day in ihsg_dates if day not in captured)
