"""
DTOs for the pre-open lane readiness pre-flight.

The pre-open lane captures the IDX NCP lock window (08:56-08:58 WIB) and is the
one lane in this system that cannot be replayed — the input phase does not exist
after 09:00. So the operative question is never "is the lane healthy now" but
"is it still going to work at 08:56, while there is time to intervene".

Two checks answer that from different directions:

* ``SESSION_TOKEN`` — a *predictive* check. Cheap, local, no network, and it
  catches the failure mode actually observed on 2026-08-07 (a reauth that left
  no usable RS256 JWT). It cannot prove Stockbit will accept the token.
* ``EARLY_FETCH`` — a *proof* check. Reads what the already-scheduled 08:47
  fetch stored, so it costs no extra API call and closes the gap the local
  check leaves open. It only becomes meaningful once that fetch is due.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum


class PreOpenReadinessCheck(str, Enum):
    SESSION_TOKEN = "SESSION_TOKEN"
    EARLY_FETCH = "EARLY_FETCH"


class PreOpenReadinessStatus(str, Enum):
    """Verdict for one check.

    ``NOT_DUE`` and ``UNKNOWN`` are deliberately distinct from ``OK``. A check
    that has not run yet, and a check whose input could not be read, are both
    silent — but neither is evidence that the lane is fine, and collapsing them
    into ``OK`` is how a watchdog starts lying.
    """

    OK = "OK"
    AT_RISK = "AT_RISK"
    NOT_DUE = "NOT_DUE"
    UNKNOWN = "UNKNOWN"


class SessionEligibility(str, Enum):
    """Whether the session date is one the pre-open lane should run at all.

    ``NO_CALENDAR_AUTHORITY`` must not be treated as a holiday. Suppressing an
    alarm because nothing attested the date would turn a missing calendar into
    silent data loss on the one lane that cannot be replayed.
    """

    TRADING_SESSION = "TRADING_SESSION"
    NOT_A_TRADING_SESSION = "NOT_A_TRADING_SESSION"
    NO_CALENDAR_AUTHORITY = "NO_CALENDAR_AUTHORITY"


@dataclass(frozen=True)
class PreOpenReadinessRow:
    check: PreOpenReadinessCheck
    status: PreOpenReadinessStatus
    detail: str
    remediation: str | None = None


@dataclass(frozen=True)
class PreOpenLaneReadinessRequest:
    """Inputs for one readiness assessment.

    ``as_of`` must be timezone-aware; the whole point of the check is a claim
    about a specific wall-clock moment relative to the NCP window, and a naive
    datetime cannot make that claim honestly.
    """

    as_of: datetime
    session_date: date | None = None
    ncp_window_end: time = time(8, 58)
    token_margin_minutes: int = 10
    early_fetch_due_at: time = time(8, 48)
    min_early_fetch_rows: int = 1


@dataclass(frozen=True)
class PreOpenLaneReadinessResponse:
    session_date: date
    as_of: datetime
    eligibility: SessionEligibility
    rows: tuple[PreOpenReadinessRow, ...]
    calendar_snapshot_ids: tuple[str, ...]

    @property
    def at_risk(self) -> tuple[PreOpenReadinessRow, ...]:
        return tuple(row for row in self.rows if row.status is PreOpenReadinessStatus.AT_RISK)

    @property
    def unknown(self) -> tuple[PreOpenReadinessRow, ...]:
        return tuple(row for row in self.rows if row.status is PreOpenReadinessStatus.UNKNOWN)

    @property
    def on_track(self) -> bool:
        """True when nothing is known to threaten today's NCP capture.

        ``UNKNOWN`` counts against being on track. On a lane where a miss is
        permanent, an unreadable check is a reason to look, not to relax.
        """
        return not self.at_risk and not self.unknown
