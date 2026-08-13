"""
Audit learning-corpus session continuity against the attested trading calendar.

The learning corpus is calendar-bound: a session that is never captured cannot
be recovered by re-running anything later for live-only purposes, and for
replayable purposes it still has to be noticed before anyone will replay it.
The cron wrapper is fail-closed, but a fail-closed job that nobody watches is
just a quiet job. This use case is the watcher.

Continuity is policy, not presentation:

* which dates were trading sessions comes from attested calendar snapshots,
  each authoritative only inside its own coverage window;
* what counts as a *hole* depends on an expected cross-sectional width;
* whether the corpus is operationally healthy depends on how far back an
  unrepaired hole should keep raising an alarm.

All three decisions live here so CLI, TUI, and cron share one answer.

Layer: Application
Depends on: Domain ports (learning observations, trading session calendar)
AI usage: None
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from math import ceil

from src.application.dto.corpus_continuity import (
    CorpusContinuityRequest,
    CorpusContinuityResponse,
    SessionContinuityRow,
    SessionContinuityStatus,
)
from src.application.services.trading_calendar_authority import CalendarAuthority
from src.domain.ports.learning_artifact_repositories import LearningObservationRepository
from src.domain.ports.trading_session_calendar_repository import (
    TradingSessionCalendarSnapshotReadRepository,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE

_SATURDAY = 5


def classify_session(
    *,
    observation_count: int,
    declared_expected_count: int | None,
    min_coverage_fraction: float,
    has_calendar_authority: bool,
    is_attested_session: bool,
) -> SessionContinuityStatus:
    """Decide one session's continuity verdict.

    Called once per candidate date inside the audit window. Confirmed
    non-trading days are filtered out before this runs, so every call is a date
    that either is an attested session or could not be attested at all.

    The policy, and why each branch is what it is:

    * **No calendar authority** — no stored snapshot's coverage window contains
      the date, so nothing attests whether the market even opened. This is
      reported as its own status rather than folded into ``OK`` or ``MISSING``:
      claiming a hole would be guessing, and claiming health would be a silent
      assumption. It does not raise the alarm, because the gap is in the
      calendar rather than in the corpus.
    * **Attested session with nothing captured** — the unambiguous failure the
      watchdog exists to catch.
    * **Attested session captured thinner than declared** — flagged only when
      the caller declared a width. A width guessed from the corpus itself
      cannot detect a systematically thin corpus, and some purposes have no
      fixed width to guess: a pre-open capture records only the candidates that
      pass its filters, so 3 one day and 5 the next are both complete.
    * **Covered but not attested, yet holding observations** — the calendar says
      this was not a trading day while the corpus holds captures for it. That is
      a calendar/corpus disagreement, not a continuity hole, and the four
      continuity statuses cannot express it. Reported ``OK`` here so a
      continuity audit does not masquerade as an integrity audit; surfacing the
      contradiction properly needs its own check.
    """
    if not has_calendar_authority:
        return SessionContinuityStatus.NO_CALENDAR_AUTHORITY
    if not is_attested_session:
        return SessionContinuityStatus.OK
    if observation_count == 0:
        return SessionContinuityStatus.MISSING
    if declared_expected_count is None:
        return SessionContinuityStatus.OK
    if observation_count < ceil(declared_expected_count * min_coverage_fraction):
        return SessionContinuityStatus.UNDER_COVERED
    return SessionContinuityStatus.OK


class AuditCorpusContinuityUseCase:
    """Report which sessions the corpus is missing for one purpose/cohort."""

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        calendar_snapshots: TradingSessionCalendarSnapshotReadRepository,
    ) -> None:
        self._observations = observations
        self._calendar_snapshots = calendar_snapshots

    def execute(self, request: CorpusContinuityRequest) -> CorpusContinuityResponse:
        counts_by_session = self._observation_counts(request)
        authority = CalendarAuthority(tuple(self._calendar_snapshots.list_snapshots()))

        window_start = request.window_start
        if window_start is None:
            window_start = min(counts_by_session) if counts_by_session else None

        declared = request.expected_observation_count
        rows = (
            self._build_rows(
                window_start=window_start,
                window_end=request.as_of,
                counts_by_session=counts_by_session,
                authority=authority,
                declared=declared,
                min_coverage_fraction=request.min_coverage_fraction,
            )
            if window_start is not None
            else ()
        )

        return CorpusContinuityResponse(
            purpose=request.purpose,
            compatibility_id=request.compatibility_id,
            window_start=window_start,
            window_end=request.as_of,
            rows=rows,
            calendar_snapshot_ids=authority.snapshot_ids,
            expected_observation_count=declared,
            observed_modal_width=_derive_modal_width(counts_by_session),
            operationally_healthy=_is_operationally_healthy(rows, request.alert_lookback_sessions),
            alert_lookback_sessions=request.alert_lookback_sessions,
        )

    def _observation_counts(self, request: CorpusContinuityRequest) -> dict[date, int]:
        observations = self._observations.list_observations(
            request.purpose, compatibility_id=request.compatibility_id
        )
        counts: Counter[date] = Counter()
        for observation in observations:
            # cutoff_at is stored tz-aware at the IDX close; normalise through
            # IDX_TIMEZONE rather than calling .date() on whatever offset the
            # row happens to carry, or sessions shift by one near midnight.
            counts[observation.cutoff_at.astimezone(IDX_TIMEZONE).date()] += 1
        return dict(counts)

    def _build_rows(
        self,
        *,
        window_start: date,
        window_end: date,
        counts_by_session: dict[date, int],
        authority: CalendarAuthority,
        declared: int | None,
        min_coverage_fraction: float,
    ) -> tuple[SessionContinuityRow, ...]:
        rows: list[SessionContinuityRow] = []
        day = window_start
        while day <= window_end:
            covered = authority.covers(day)
            attested = covered and authority.is_session(day)
            observed = counts_by_session.get(day, 0)

            if not _is_candidate_date(
                covered=covered, attested=attested, observed=observed, day=day
            ):
                day += timedelta(days=1)
                continue

            rows.append(
                SessionContinuityRow(
                    session_date=day,
                    status=classify_session(
                        observation_count=observed,
                        declared_expected_count=declared,
                        min_coverage_fraction=min_coverage_fraction,
                        has_calendar_authority=covered,
                        is_attested_session=attested,
                    ),
                    observation_count=observed,
                    expected_observation_count=declared,
                )
            )
            day += timedelta(days=1)
        return tuple(rows)


def _is_candidate_date(*, covered: bool, attested: bool, observed: int, day: date) -> bool:
    """Whether a date is worth judging at all.

    A covered date that the calendar does not list is a confirmed market
    holiday or weekend — silence there is correct, so it is dropped rather than
    reported. Where no snapshot covers the date there is nothing to confirm
    with, and the weekday check below is an explicitly bounded fallback used
    *only* in that gap: it can misjudge an uncovered public holiday, which is
    why such dates are surfaced as unattestable instead of as failures.
    """
    if covered:
        return attested or observed > 0
    return observed > 0 or day.weekday() < _SATURDAY


def _derive_modal_width(counts_by_session: dict[date, int]) -> int | None:
    """Modal per-session observation count across sessions that captured anything.

    Reported for information only — never used to judge a session. The mode, not
    the max: one backfill that over-collected must not redefine every ordinary
    session as thin.
    """
    populated = [count for count in counts_by_session.values() if count > 0]
    if not populated:
        return None
    return Counter(populated).most_common(1)[0][0]


def _is_operationally_healthy(
    rows: tuple[SessionContinuityRow, ...], alert_lookback_sessions: int | None
) -> bool:
    """Fail-closed health predicate over the alerting horizon.

    With ``alert_lookback_sessions`` set, only that many most recent sessions
    are considered, so a known-unrepairable historical hole stops re-alerting
    every day while a fresh failure still fires. With ``None`` the whole window
    must be clean.
    """
    considered = rows if alert_lookback_sessions is None else rows[-alert_lookback_sessions:]
    return all(
        row.status in (SessionContinuityStatus.OK, SessionContinuityStatus.NO_CALENDAR_AUTHORITY)
        for row in considered
    )
