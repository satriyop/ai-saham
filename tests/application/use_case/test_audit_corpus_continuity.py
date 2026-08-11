"""
Continuity audit tests for the learning corpus.

The audit answers "which trading sessions is this cohort missing?" and feeds a
cron alarm, so its failure modes are the interesting part: a hole it does not
report is a silently lost session, and a hole it invents wakes the operator for
nothing.

The load-bearing case is `test_fragmented_snapshots_are_unioned`. Trading
session calendar snapshots are rolling ~30-day windows attested per coverage
range, so no single snapshot spans a mature corpus. An implementation that reads
only the newest snapshot looks correct on a young corpus and goes blind on the
oldest sessions of a mature one.

All dates are FIXED. All fakes are in-memory. No network.
"""

from datetime import date, datetime, timezone

import pytest

from src.application.dto.corpus_continuity import (
    CorpusContinuityRequest,
    SessionContinuityStatus,
)
from src.application.use_case.audit_corpus_continuity_use_case import (
    AuditCorpusContinuityUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)

_PURPOSE = AssessmentPurpose.ACCUMULATION_DISCOVERY
_COHORT = "sha256:testcohort"
_WIDTH = 45

# 2026-07-08 (Wed) .. 2026-07-10 (Fri), then 2026-07-13 (Mon) .. 2026-07-15 (Wed).
_SESSIONS = (
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
)


def _observation(session: date, index: int, *, at: datetime | None = None) -> LearningObservation:
    """One window-observation for `session`. `index` keeps identities distinct."""
    cutoff = at or datetime.combine(session, datetime.min.time(), IDX_TIMEZONE).replace(hour=16)
    return LearningObservation.create(
        purpose=_PURPOSE,
        policy_contract="policy.test.v1",
        horizon_contract="horizon.test.v1",
        compatibility_id=_COHORT,
        cutoff_at=cutoff,
        universe_id="lq45",
        window_id=f"w{index}",
        decision_payload={"n": index},
        captured_at=cutoff,
        producer_source_revision="testrev",
    )


class _FakeObservations:
    def __init__(self, observations: list[LearningObservation]) -> None:
        self._observations = observations

    def list_observations(self, purpose, *, compatibility_id=None):
        return [
            observation
            for observation in self._observations
            if observation.purpose is purpose
            and (compatibility_id is None or observation.compatibility_id == compatibility_id)
        ]

    def add_observation(self, artifact):  # pragma: no cover - unused by the audit
        raise NotImplementedError

    def get_observation(self, observation_id):  # pragma: no cover - unused by the audit
        raise NotImplementedError


class _FakeCalendar:
    def __init__(self, snapshots: list[TradingSessionCalendarSnapshot]) -> None:
        self._snapshots = snapshots

    def list_snapshots(self):
        return list(self._snapshots)

    def get_snapshot(self, snapshot_id):  # pragma: no cover - unused by the audit
        raise NotImplementedError


def _snapshot(
    coverage_start: date, coverage_end: date, sessions: tuple[date, ...], revision: str
) -> TradingSessionCalendarSnapshot:
    return TradingSessionCalendarSnapshot.create(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        ordered_sessions=sessions,
        source_revision=revision,
        captured_at=datetime(2026, 7, 16, 19, 0, tzinfo=IDX_TIMEZONE),
    )


def _full_snapshot() -> TradingSessionCalendarSnapshot:
    return _snapshot(_SESSIONS[0], _SESSIONS[-1], _SESSIONS, "r-full")


def _audit(
    observations: list[LearningObservation],
    snapshots: list[TradingSessionCalendarSnapshot],
    **request_kwargs,
):
    use_case = AuditCorpusContinuityUseCase(
        observations=_FakeObservations(observations),
        calendar_snapshots=_FakeCalendar(snapshots),
    )
    request_kwargs.setdefault("as_of", _SESSIONS[-1])
    request_kwargs.setdefault("expected_observation_count", _WIDTH)
    return use_case.execute(
        CorpusContinuityRequest(purpose=_PURPOSE, compatibility_id=_COHORT, **request_kwargs)
    )


def _corpus(sessions: tuple[date, ...], width: int = _WIDTH) -> list[LearningObservation]:
    return [_observation(session, index) for session in sessions for index in range(width)]


def _status_by_date(response) -> dict[date, SessionContinuityStatus]:
    return {row.session_date: row.status for row in response.rows}


def test_clean_corpus_reports_every_session_ok() -> None:
    response = _audit(_corpus(_SESSIONS), [_full_snapshot()])

    assert len(response.rows) == len(_SESSIONS)
    assert set(_status_by_date(response).values()) == {SessionContinuityStatus.OK}
    assert response.operationally_healthy is True


def test_missing_session_is_detected_and_fails_health() -> None:
    kept = tuple(session for session in _SESSIONS if session != date(2026, 7, 10))

    response = _audit(_corpus(kept), [_full_snapshot()])

    assert response.missing_sessions == (date(2026, 7, 10),)
    assert response.operationally_healthy is False


def test_suspension_tolerance_keeps_a_44_of_45_session_ok() -> None:
    observations = _corpus(_SESSIONS[:-1]) + _corpus((_SESSIONS[-1],), width=44)

    response = _audit(observations, [_full_snapshot()])

    assert _status_by_date(response)[_SESSIONS[-1]] is SessionContinuityStatus.OK
    assert response.operationally_healthy is True


@pytest.mark.parametrize(
    ("width", "expected"),
    [
        (41, SessionContinuityStatus.OK),  # ceil(45 * 0.9) == 41, the boundary
        (40, SessionContinuityStatus.UNDER_COVERED),
        (3, SessionContinuityStatus.UNDER_COVERED),
    ],
)
def test_coverage_fraction_boundary(width: int, expected: SessionContinuityStatus) -> None:
    observations = _corpus(_SESSIONS[:-1]) + _corpus((_SESSIONS[-1],), width=width)

    response = _audit(observations, [_full_snapshot()])

    assert _status_by_date(response)[_SESSIONS[-1]] is expected


def test_fragmented_snapshots_are_unioned() -> None:
    """Neither snapshot spans the corpus; together they must attest all of it.

    Reading only the newest snapshot would leave 2026-07-08..09 uncovered and
    report them as unattestable, hiding a real hole on 07-09.
    """
    older = _snapshot(_SESSIONS[0], _SESSIONS[2], _SESSIONS[:3], "r-old")
    newer = _snapshot(_SESSIONS[2], _SESSIONS[-1], _SESSIONS[2:], "r-new")
    kept = tuple(session for session in _SESSIONS if session != date(2026, 7, 9))

    response = _audit(_corpus(kept), [newer, older])

    statuses = _status_by_date(response)
    assert statuses[date(2026, 7, 8)] is SessionContinuityStatus.OK
    assert statuses[date(2026, 7, 9)] is SessionContinuityStatus.MISSING
    assert response.unattestable_sessions == ()
    assert len(response.calendar_snapshot_ids) == 2


def test_uncovered_date_is_unattestable_and_does_not_raise_the_alarm() -> None:
    """A calendar gap is a calendar problem, not a corpus hole."""
    partial = _snapshot(_SESSIONS[0], _SESSIONS[2], _SESSIONS[:3], "r-part")

    response = _audit(_corpus(_SESSIONS[:3]), [partial])

    statuses = _status_by_date(response)
    assert statuses[date(2026, 7, 13)] is SessionContinuityStatus.NO_CALENDAR_AUTHORITY
    assert response.missing_sessions == ()
    assert response.operationally_healthy is True


def test_market_holiday_inside_coverage_produces_no_row() -> None:
    """A covered date the calendar omits is a confirmed non-session: stay silent."""
    holiday = date(2026, 7, 9)
    sessions = tuple(session for session in _SESSIONS if session != holiday)
    snapshot = _snapshot(_SESSIONS[0], _SESSIONS[-1], sessions, "r-holiday")

    response = _audit(_corpus(sessions), [snapshot])

    assert holiday not in _status_by_date(response)
    assert response.operationally_healthy is True


def test_cutoff_at_is_normalised_through_idx_timezone() -> None:
    """A UTC cutoff that lands on the next IDX day must count as that IDX session.

    Calling .date() on the stored offset instead of converting would file this
    observation one day early and invent a hole.
    """
    session = date(2026, 7, 15)
    utc_cutoff = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
    assert utc_cutoff.astimezone(IDX_TIMEZONE).date() == session
    assert utc_cutoff.date() != session

    observations = _corpus(_SESSIONS[:-1]) + [
        _observation(session, index, at=utc_cutoff) for index in range(_WIDTH)
    ]

    response = _audit(observations, [_full_snapshot()])

    assert _status_by_date(response)[session] is SessionContinuityStatus.OK
    assert response.missing_sessions == ()


def test_alert_lookback_ignores_an_old_hole_but_catches_a_recent_one() -> None:
    without_first = tuple(session for session in _SESSIONS if session != _SESSIONS[0])

    stale = _audit(
        _corpus(without_first),
        [_full_snapshot()],
        window_start=_SESSIONS[0],
        alert_lookback_sessions=3,
    )
    assert stale.missing_sessions == (_SESSIONS[0],)
    assert stale.operationally_healthy is True

    without_last = tuple(session for session in _SESSIONS if session != _SESSIONS[-1])
    fresh = _audit(_corpus(without_last), [_full_snapshot()], alert_lookback_sessions=3)
    assert fresh.operationally_healthy is False


def test_empty_corpus_returns_no_rows() -> None:
    response = _audit([], [_full_snapshot()])

    assert response.rows == ()
    assert response.window_start is None
    assert response.observed_modal_width is None
    assert response.operationally_healthy is True


def test_undeclared_width_never_flags_under_covered() -> None:
    """Pre-open captures only what passes its filters; there is no width to expect."""
    observations = _corpus(_SESSIONS[:-1]) + _corpus((_SESSIONS[-1],), width=1)

    response = _audit(observations, [_full_snapshot()], expected_observation_count=None)

    assert response.under_covered_sessions == ()
    assert response.operationally_healthy is True
    assert _status_by_date(response)[_SESSIONS[-1]] is SessionContinuityStatus.OK


def test_undeclared_width_still_detects_a_wholly_missing_session() -> None:
    kept = tuple(session for session in _SESSIONS if session != date(2026, 7, 13))

    response = _audit(_corpus(kept), [_full_snapshot()], expected_observation_count=None)

    assert response.missing_sessions == (date(2026, 7, 13),)
    assert response.operationally_healthy is False


def test_modal_width_is_informational_and_uses_mode_not_max() -> None:
    """One over-collecting backfill must not redefine every ordinary session as thin."""
    observations = _corpus(_SESSIONS[:-1]) + _corpus((_SESSIONS[-1],), width=90)

    response = _audit(observations, [_full_snapshot()], expected_observation_count=None)

    assert response.observed_modal_width == _WIDTH
    assert response.under_covered_sessions == ()


def test_window_start_defaults_to_the_first_observed_session() -> None:
    """The audit must not report all of market history before the cohort began."""
    response = _audit(_corpus(_SESSIONS[2:]), [_full_snapshot()])

    assert response.window_start == _SESSIONS[2]
    assert response.missing_sessions == ()


def test_explicit_window_start_exposes_sessions_before_the_first_capture() -> None:
    response = _audit(_corpus(_SESSIONS[2:]), [_full_snapshot()], window_start=_SESSIONS[0])

    assert response.missing_sessions == (_SESSIONS[0], _SESSIONS[1])
    assert response.operationally_healthy is False


def test_counts_tally_every_status() -> None:
    response = _audit(_corpus(_SESSIONS), [_full_snapshot()])

    counts = response.counts()
    assert counts[SessionContinuityStatus.OK.value] == len(_SESSIONS)
    assert sum(counts.values()) == len(response.rows)


def test_weekend_in_a_calendar_gap_is_not_reported() -> None:
    """The uncovered-date fallback must not invent Saturday and Sunday sessions."""
    partial = _snapshot(_SESSIONS[0], _SESSIONS[2], _SESSIONS[:3], "r-part")
    saturday = date(2026, 7, 11)
    sunday = date(2026, 7, 12)
    assert saturday.weekday() == 5 and sunday.weekday() == 6

    response = _audit(_corpus(_SESSIONS[:3]), [partial])

    reported = _status_by_date(response)
    assert saturday not in reported
    assert sunday not in reported


def test_cohort_filter_excludes_other_compatibility_ids() -> None:
    foreign = LearningObservation.create(
        purpose=_PURPOSE,
        policy_contract="policy.test.v1",
        horizon_contract="horizon.test.v1",
        compatibility_id="sha256:othercohort",
        cutoff_at=datetime.combine(_SESSIONS[0], datetime.min.time(), IDX_TIMEZONE).replace(
            hour=16
        ),
        universe_id="lq45",
        window_id="w0",
        decision_payload={"n": 0},
        captured_at=datetime(2026, 7, 8, 19, 0, tzinfo=IDX_TIMEZONE),
        producer_source_revision="testrev",
    )
    kept = tuple(session for session in _SESSIONS if session != _SESSIONS[0])

    response = _audit(_corpus(kept) + [foreign], [_full_snapshot()], window_start=_SESSIONS[0])

    assert response.missing_sessions == (_SESSIONS[0],)


def test_as_of_before_the_last_session_truncates_the_window() -> None:
    response = _audit(_corpus(_SESSIONS[:3]), [_full_snapshot()], as_of=_SESSIONS[2])

    assert response.window_end == _SESSIONS[2]
    assert len(response.rows) == 3
    assert response.operationally_healthy is True


def test_future_as_of_reports_the_uncaptured_tail_as_missing() -> None:
    """Running the audit after a failed capture must show today as a hole."""
    response = _audit(_corpus(_SESSIONS[:-1]), [_full_snapshot()])

    assert response.missing_sessions == (_SESSIONS[-1],)
    assert response.operationally_healthy is False


def test_lookback_larger_than_the_window_considers_everything() -> None:
    kept = tuple(session for session in _SESSIONS if session != _SESSIONS[0])

    response = _audit(
        _corpus(kept), [_full_snapshot()], window_start=_SESSIONS[0], alert_lookback_sessions=999
    )

    assert response.operationally_healthy is False


def test_snapshot_ids_are_reported_for_provenance() -> None:
    older = _snapshot(_SESSIONS[0], _SESSIONS[2], _SESSIONS[:3], "r-old")
    newer = _snapshot(_SESSIONS[2], _SESSIONS[-1], _SESSIONS[2:], "r-new")

    response = _audit(_corpus(_SESSIONS), [newer, older])

    assert response.calendar_snapshot_ids == tuple(sorted((older.snapshot_id, newer.snapshot_id)))


def test_no_calendar_snapshots_at_all_makes_everything_unattestable() -> None:
    response = _audit(_corpus(_SESSIONS), [])

    assert set(_status_by_date(response).values()) == {
        SessionContinuityStatus.NO_CALENDAR_AUTHORITY
    }
    assert response.missing_sessions == ()
    assert response.calendar_snapshot_ids == ()


def test_gap_between_two_snapshots_is_unattestable_not_missing() -> None:
    """Coverage union must not silently bridge a hole between two windows."""
    first = _snapshot(_SESSIONS[0], _SESSIONS[1], _SESSIONS[:2], "r-a")
    third = _snapshot(_SESSIONS[3], _SESSIONS[-1], _SESSIONS[3:], "r-b")

    response = _audit(_corpus(_SESSIONS), [first, third])

    statuses = _status_by_date(response)
    assert statuses[_SESSIONS[2]] is SessionContinuityStatus.NO_CALENDAR_AUTHORITY
    assert response.missing_sessions == ()


def test_row_order_follows_the_calendar() -> None:
    response = _audit(_corpus(_SESSIONS), [_full_snapshot()])

    dates = [row.session_date for row in response.rows]
    assert dates == sorted(dates)
    assert dates[0] == _SESSIONS[0]


def test_session_gap_of_a_weekend_does_not_create_rows() -> None:
    response = _audit(_corpus(_SESSIONS), [_full_snapshot()])

    assert date(2026, 7, 11) not in _status_by_date(response)
    assert len(response.rows) == len(_SESSIONS)


def test_alert_lookback_of_one_watches_only_the_latest_session() -> None:
    without_middle = tuple(session for session in _SESSIONS if session != _SESSIONS[2])

    response = _audit(_corpus(without_middle), [_full_snapshot()], alert_lookback_sessions=1)

    assert response.missing_sessions == (_SESSIONS[2],)
    assert response.operationally_healthy is True


def test_declared_width_is_echoed_on_every_row() -> None:
    response = _audit(_corpus(_SESSIONS), [_full_snapshot()])

    assert {row.expected_observation_count for row in response.rows} == {_WIDTH}
    assert response.expected_observation_count == _WIDTH


def test_min_coverage_fraction_is_configurable() -> None:
    observations = _corpus(_SESSIONS[:-1]) + _corpus((_SESSIONS[-1],), width=40)

    tolerant = _audit(observations, [_full_snapshot()], min_coverage_fraction=0.5)
    strict = _audit(observations, [_full_snapshot()], min_coverage_fraction=1.0)

    assert _status_by_date(tolerant)[_SESSIONS[-1]] is SessionContinuityStatus.OK
    assert _status_by_date(strict)[_SESSIONS[-1]] is SessionContinuityStatus.UNDER_COVERED


def test_audit_is_deterministic_for_the_same_inputs() -> None:
    observations = _corpus(_SESSIONS)
    snapshots = [_full_snapshot()]

    first = _audit(observations, snapshots)
    second = _audit(observations, snapshots)

    assert first == second


def test_one_day_window_with_a_single_session() -> None:
    response = _audit(
        _corpus((_SESSIONS[0],)),
        [_full_snapshot()],
        as_of=_SESSIONS[0],
    )

    assert len(response.rows) == 1
    assert response.rows[0].status is SessionContinuityStatus.OK


def test_observation_dated_after_as_of_is_not_counted_in_the_window() -> None:
    """A late capture must not backfill the appearance of health."""
    response = _audit(_corpus(_SESSIONS), [_full_snapshot()], as_of=_SESSIONS[1])

    assert response.window_end == _SESSIONS[1]
    assert [row.session_date for row in response.rows] == list(_SESSIONS[:2])


def test_day_walk_handles_a_month_boundary() -> None:
    """The day-by-day walk must cross a month boundary and a weekend intact.

    Thu 2026-07-30, Fri 07-31, Mon 08-03 are real IDX sessions; Sat 08-01 and
    Sun 08-02 fall inside coverage and must produce no rows.
    """
    long_sessions = (date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 3))
    snapshot = _snapshot(long_sessions[0], long_sessions[-1], long_sessions, "r-long")

    response = _audit(
        _corpus(long_sessions),
        [snapshot],
        as_of=long_sessions[-1],
        window_start=long_sessions[0],
    )

    assert len(response.rows) == len(long_sessions)
    assert response.operationally_healthy is True
