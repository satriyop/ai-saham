"""
Assess whether today's pre-open lane will still work when the NCP window opens.

The pre-open lane is the only unrecoverable capture in this system. The accum
corpus can be rebuilt with ``signal-backfill-observations``; the 08:56-08:58 NCP
snapshot cannot, because the input phase is gone by 09:00. Session 2026-08-07 is
absent from ``iev_snapshots`` for exactly this reason and will stay absent.

So the corpus continuity watchdog, which runs at 19:30, is structurally unable
to help this lane: it reports the loss eleven hours after the last moment
anything could have been done. This use case is the same idea moved to where it
can still change the outcome — before 08:56, while
``saham fetch stockbit reauth --mode headed`` is still a live option.

Everything here is policy, which is why it is not in the cron script:

* what "still usable at the NCP window" means (a token valid now but expiring
  at 08:50 is a failure, not a pass);
* how much margin past the window close is required;
* when the fetch-proof check becomes due, and what it means before then;
* whether a non-trading day suppresses the alarm, and — separately — whether an
  unattested one does. It must not.

**Known limitation — holiday false alarms.** Calendar snapshots are built from
realised sessions and synced at 19:18 with ``coverage_end`` set to that same
day, so at 08:41 *today is always outside coverage* and eligibility resolves to
``NO_CALENDAR_AUTHORITY``. The ``NOT_A_TRADING_SESSION`` branch is therefore
unreachable at pre-flight time in production; it exists for explicit
``--session`` back-checks and for the day a forward-looking calendar lands.

The consequence is real and is not papered over: on an IDX public holiday the
cron still fires, no IEV rows appear, and ``EARLY_FETCH`` raises a false alarm.
There is no offline same-day holiday authority in this repo to prevent it —
``src/domain/services/trading_calendar.py`` states that no holiday calendar is
maintained. Roughly 15-20 weekday holidays a year means roughly that many false
alarms, so the operator-facing message names the possibility explicitly rather
than letting a wrong alarm look like a real one. Fixing it properly needs a
forward-looking session calendar, which is out of scope here.

Layer: Application
Depends on: Domain ports (IEV snapshot count, trading session calendar);
            application DTO for Stockbit session status
AI usage: None
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from src.application.dto.preopen_lane_readiness import (
    PreOpenLaneReadinessRequest,
    PreOpenLaneReadinessResponse,
    PreOpenReadinessCheck,
    PreOpenReadinessRow,
    PreOpenReadinessStatus,
    SessionEligibility,
)
from src.application.services.stockbit_session import StockbitSessionStatus
from src.application.services.trading_calendar_authority import CalendarAuthority
from src.domain.ports.preopen_iev_snapshot_repository import PreOpenIevSnapshotCountPort
from src.domain.ports.trading_session_calendar_repository import (
    TradingSessionCalendarSnapshotReadRepository,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE

_REAUTH_REMEDIATION = "saham fetch stockbit reauth --mode headed"
_FETCH_REMEDIATION = "saham fetch stockbit reauth --mode headed && saham fetch iev"


def classify_session_token(
    *,
    status: StockbitSessionStatus,
    seconds_required: float,
) -> tuple[PreOpenReadinessStatus, str]:
    """Decide whether the saved session survives long enough to be useful.

    ``seconds_required`` is the distance from now to the moment the token stops
    mattering — the NCP window close plus margin — not an arbitrary threshold.
    Comparing against remaining lifetime rather than a fixed floor is what makes
    this predictive: the measured token TTL is exactly 24h from each 08:40
    reauth, so a failed reauth leaves yesterday's token expiring *inside* the
    pre-open lane while still reading "valid" for a few more minutes.

    ``seconds_required <= 0`` means the window has already closed, so the check
    can no longer predict anything worth acting on.
    """
    if not status.profile_exists:
        return (
            PreOpenReadinessStatus.AT_RISK,
            f"no browser profile at {status.profile_path}",
        )
    if not status.token_exists or status.token_state == "missing":
        return PreOpenReadinessStatus.AT_RISK, "no saved Exodus JWT"
    if status.token_state == "invalid":
        return PreOpenReadinessStatus.AT_RISK, "saved JWT is not a usable RS256 token"
    if status.token_state == "expired":
        return PreOpenReadinessStatus.AT_RISK, "saved JWT has expired"
    if seconds_required <= 0:
        return (
            PreOpenReadinessStatus.NOT_DUE,
            "NCP window has already closed for this session",
        )
    if status.token_seconds_remaining is None:
        # Reported valid but with no expiry to reason about. Not provably bad,
        # and explicitly not OK — see PreOpenReadinessStatus.UNKNOWN.
        return (
            PreOpenReadinessStatus.UNKNOWN,
            "token reports valid but carries no expiry",
        )
    if status.token_seconds_remaining < seconds_required:
        return (
            PreOpenReadinessStatus.AT_RISK,
            (
                f"token expires in {status.token_seconds_remaining // 60} min, "
                f"needs {int(seconds_required) // 60} min to cover the NCP window"
            ),
        )
    return (
        PreOpenReadinessStatus.OK,
        f"token valid for {status.token_seconds_remaining // 60} more min",
    )


def classify_early_fetch(
    *,
    is_due: bool,
    row_count: int,
    minimum_rows: int,
    due_at_label: str,
) -> tuple[PreOpenReadinessStatus, str]:
    """Decide whether the scheduled early fetch actually produced data.

    This is the half the local token check cannot cover: ``fetch iev`` prints
    "No movers returned" and exits 0, so a token Stockbit rejects looks exactly
    like a healthy run from outside. Stored rows are the only honest proof.
    """
    if not is_due:
        return (
            PreOpenReadinessStatus.NOT_DUE,
            f"early fetch not expected before {due_at_label}",
        )
    if row_count < minimum_rows:
        return (
            PreOpenReadinessStatus.AT_RISK,
            f"{row_count} IEV rows stored, expected at least {minimum_rows}",
        )
    return PreOpenReadinessStatus.OK, f"{row_count} IEV rows stored"


class AssessPreOpenLaneReadinessUseCase:
    """Report whether today's NCP capture is still on track."""

    def __init__(
        self,
        *,
        iev_snapshots: PreOpenIevSnapshotCountPort,
        calendar_snapshots: TradingSessionCalendarSnapshotReadRepository,
        session_status: Callable[[], StockbitSessionStatus],
    ) -> None:
        self._iev_snapshots = iev_snapshots
        self._calendar_snapshots = calendar_snapshots
        self._session_status = session_status

    def execute(self, request: PreOpenLaneReadinessRequest) -> PreOpenLaneReadinessResponse:
        as_of = _require_aware(request.as_of).astimezone(IDX_TIMEZONE)
        session_date = request.session_date or as_of.date()

        authority = CalendarAuthority(tuple(self._calendar_snapshots.list_snapshots()))
        eligibility = _classify_eligibility(authority, session_date)

        if eligibility is SessionEligibility.NOT_A_TRADING_SESSION:
            # The market is closed; there is nothing to capture and nothing to
            # alarm about. Reported with no rows rather than rows of OK, so the
            # output cannot be mistaken for a lane that was checked and passed.
            return PreOpenLaneReadinessResponse(
                session_date=session_date,
                as_of=as_of,
                eligibility=eligibility,
                rows=(),
                calendar_snapshot_ids=authority.snapshot_ids,
            )

        return PreOpenLaneReadinessResponse(
            session_date=session_date,
            as_of=as_of,
            eligibility=eligibility,
            rows=(
                self._token_row(request, as_of=as_of, session_date=session_date),
                self._early_fetch_row(request, as_of=as_of, session_date=session_date),
            ),
            calendar_snapshot_ids=authority.snapshot_ids,
        )

    def _token_row(
        self,
        request: PreOpenLaneReadinessRequest,
        *,
        as_of: datetime,
        session_date: date,
    ) -> PreOpenReadinessRow:
        deadline = datetime.combine(
            session_date, request.ncp_window_end, tzinfo=IDX_TIMEZONE
        ) + timedelta(minutes=request.token_margin_minutes)

        try:
            status = self._session_status()
        except Exception as exc:  # noqa: BLE001 - surfaced as UNKNOWN, never as OK
            # A checker that cannot read its own input must say so. Returning OK
            # here would be the exact failure this task exists to remove.
            return PreOpenReadinessRow(
                check=PreOpenReadinessCheck.SESSION_TOKEN,
                status=PreOpenReadinessStatus.UNKNOWN,
                detail=f"could not read session status: {exc}",
                remediation=_REAUTH_REMEDIATION,
            )

        verdict, detail = classify_session_token(
            status=status,
            seconds_required=(deadline - as_of).total_seconds(),
        )
        return PreOpenReadinessRow(
            check=PreOpenReadinessCheck.SESSION_TOKEN,
            status=verdict,
            detail=detail,
            remediation=(_REAUTH_REMEDIATION if verdict is not PreOpenReadinessStatus.OK else None),
        )

    def _early_fetch_row(
        self,
        request: PreOpenLaneReadinessRequest,
        *,
        as_of: datetime,
        session_date: date,
    ) -> PreOpenReadinessRow:
        due_at = datetime.combine(session_date, request.early_fetch_due_at, tzinfo=IDX_TIMEZONE)
        is_due = as_of >= due_at

        row_count = 0
        if is_due:
            try:
                row_count = self._iev_snapshots.count_snapshot_rows(session_date)
            except Exception as exc:  # noqa: BLE001 - surfaced as UNKNOWN, never as OK
                return PreOpenReadinessRow(
                    check=PreOpenReadinessCheck.EARLY_FETCH,
                    status=PreOpenReadinessStatus.UNKNOWN,
                    detail=f"could not read IEV snapshots: {exc}",
                    remediation=_FETCH_REMEDIATION,
                )

        verdict, detail = classify_early_fetch(
            is_due=is_due,
            row_count=row_count,
            minimum_rows=request.min_early_fetch_rows,
            due_at_label=request.early_fetch_due_at.strftime("%H:%M"),
        )
        return PreOpenReadinessRow(
            check=PreOpenReadinessCheck.EARLY_FETCH,
            status=verdict,
            detail=detail,
            remediation=(_FETCH_REMEDIATION if verdict is PreOpenReadinessStatus.AT_RISK else None),
        )


def _classify_eligibility(authority: CalendarAuthority, session_date: date) -> SessionEligibility:
    if not authority.covers(session_date):
        return SessionEligibility.NO_CALENDAR_AUTHORITY
    if not authority.is_session(session_date):
        return SessionEligibility.NOT_A_TRADING_SESSION
    return SessionEligibility.TRADING_SESSION


def _require_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(
            "as_of must be timezone-aware: readiness is a claim about a "
            "wall-clock moment relative to the NCP window"
        )
    return moment
