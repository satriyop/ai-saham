"""
Readiness tests for the pre-open lane pre-flight.

This check guards the one capture in the system that cannot be replayed, so its
two failure directions are not symmetric and the tests are weighted accordingly:

* a miss the check reports as OK costs a permanently lost session;
* a false alarm costs the operator's trust, after which every later alarm is
  ignored and the first cost applies anyway.

So the load-bearing cases are the ones where the check is tempted to say OK
without grounds: an unreadable input, a token that is valid *now* but expires
inside the NCP window, and a date no calendar attests.

All datetimes are FIXED and timezone-aware. All fakes are in-memory. No network.
"""

from datetime import date, datetime, time, timezone

import pytest

from src.application.dto.preopen_lane_readiness import (
    PreOpenLaneReadinessRequest,
    PreOpenReadinessCheck,
    PreOpenReadinessStatus,
    SessionEligibility,
)
from src.application.services.stockbit_session import StockbitSessionStatus
from src.application.use_case.assess_preopen_lane_readiness_use_case import (
    AssessPreOpenLaneReadinessUseCase,
    classify_early_fetch,
    classify_session_token,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)

# 2026-08-13 is a Thursday and a real IDX session; 2026-08-17 (Mon) is
# Indonesian Independence Day, a genuine holiday inside a working week.
_SESSION = date(2026, 8, 13)
_HOLIDAY = date(2026, 8, 17)
_SESSIONS = (date(2026, 8, 11), date(2026, 8, 12), _SESSION, date(2026, 8, 14))

_PREFLIGHT_AT = datetime(2026, 8, 13, 8, 41, tzinfo=IDX_TIMEZONE)
_VERIFY_AT = datetime(2026, 8, 13, 8, 48, tzinfo=IDX_TIMEZONE)


def _status(
    *,
    token_state="valid",
    seconds_remaining: int | None = 86_400,
    profile_exists: bool = True,
    token_exists: bool = True,
) -> StockbitSessionStatus:
    return StockbitSessionStatus(
        profile_exists=profile_exists,
        profile_path=".stockbit_profile",
        browser_login_age_hours=1.0,
        token_exists=token_exists,
        token_state=token_state,
        token_expires_at="2026-08-14T01:40:11+00:00",
        token_seconds_remaining=seconds_remaining,
        token_expiry_source="jwt_exp",
    )


class _FakeCalendar:
    def __init__(self, snapshots: list[TradingSessionCalendarSnapshot]) -> None:
        self._snapshots = snapshots

    def list_snapshots(self):
        return list(self._snapshots)

    def get_snapshot(self, snapshot_id):  # pragma: no cover - unused here
        raise NotImplementedError


class _FakeIev:
    def __init__(self, counts: dict[date, int], *, raises: bool = False) -> None:
        self._counts = counts
        self._raises = raises
        self.calls: list[date] = []

    def count_snapshot_rows(self, snapshot_date: date) -> int:
        self.calls.append(snapshot_date)
        if self._raises:
            raise RuntimeError("database is locked")
        return self._counts.get(snapshot_date, 0)


def _snapshot(
    coverage_start: date = date(2026, 8, 10),
    coverage_end: date = date(2026, 8, 20),
    sessions: tuple[date, ...] = _SESSIONS,
) -> TradingSessionCalendarSnapshot:
    return TradingSessionCalendarSnapshot.create(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        ordered_sessions=sessions,
        source_revision="testrev",
        captured_at=datetime(2026, 8, 12, 19, 0, tzinfo=IDX_TIMEZONE),
    )


def _use_case(
    *,
    iev: _FakeIev | None = None,
    calendar: _FakeCalendar | None = None,
    status=None,
) -> AssessPreOpenLaneReadinessUseCase:
    return AssessPreOpenLaneReadinessUseCase(
        iev_snapshots=iev or _FakeIev({_SESSION: 61}),
        calendar_snapshots=calendar or _FakeCalendar([_snapshot()]),
        session_status=status or (lambda: _status()),
    )


def _row(response, check: PreOpenReadinessCheck):
    return next(row for row in response.rows if row.check is check)


# --------------------------------------------------------------------------
# classify_session_token — the predictive half
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected_fragment"),
    [
        ({"profile_exists": False}, "no browser profile"),
        ({"token_exists": False}, "no saved Exodus JWT"),
        ({"token_state": "missing"}, "no saved Exodus JWT"),
        ({"token_state": "invalid"}, "not a usable RS256"),
        ({"token_state": "expired"}, "has expired"),
    ],
)
def test_unusable_sessions_are_at_risk(kwargs, expected_fragment):
    verdict, detail = classify_session_token(status=_status(**kwargs), seconds_required=1_200)
    assert verdict is PreOpenReadinessStatus.AT_RISK
    assert expected_fragment in detail


def test_token_valid_now_but_expiring_inside_the_window_is_at_risk():
    """The whole reason this check is predictive rather than a liveness probe.

    A failed 08:40 reauth leaves yesterday's token, which reads `valid` for a
    few more minutes and then dies during the pre-open lane. Reporting OK here
    would pass the check and still lose the session.
    """
    verdict, detail = classify_session_token(
        status=_status(seconds_remaining=300),  # 5 min left
        seconds_required=1_620,  # needs 27 min to cover 08:58 + margin
    )
    assert verdict is PreOpenReadinessStatus.AT_RISK
    assert "5 min" in detail and "27 min" in detail


def test_remaining_exactly_equal_to_required_is_ok():
    """Boundary: the token survives to the exact moment it stops mattering."""
    verdict, _ = classify_session_token(
        status=_status(seconds_remaining=1_620), seconds_required=1_620
    )
    assert verdict is PreOpenReadinessStatus.OK


def test_valid_token_without_an_expiry_is_unknown_not_ok():
    verdict, detail = classify_session_token(
        status=_status(seconds_remaining=None), seconds_required=1_200
    )
    assert verdict is PreOpenReadinessStatus.UNKNOWN
    assert "no expiry" in detail


def test_after_the_window_closes_the_token_check_is_not_due():
    verdict, _ = classify_session_token(status=_status(), seconds_required=-60)
    assert verdict is PreOpenReadinessStatus.NOT_DUE


def test_an_expired_token_is_at_risk_even_after_the_window_closed():
    """Order matters: a broken session is worth reporting whenever it is seen."""
    verdict, _ = classify_session_token(status=_status(token_state="expired"), seconds_required=-60)
    assert verdict is PreOpenReadinessStatus.AT_RISK


# --------------------------------------------------------------------------
# classify_early_fetch — the proof half
# --------------------------------------------------------------------------


def test_early_fetch_before_it_is_due_is_not_due():
    verdict, detail = classify_early_fetch(
        is_due=False, row_count=0, minimum_rows=1, due_at_label="08:48"
    )
    assert verdict is PreOpenReadinessStatus.NOT_DUE
    assert "08:48" in detail


def test_early_fetch_due_with_nothing_stored_is_at_risk():
    """The 2026-08-07 failure: `fetch iev` exits 0 having stored nothing."""
    verdict, detail = classify_early_fetch(
        is_due=True, row_count=0, minimum_rows=1, due_at_label="08:48"
    )
    assert verdict is PreOpenReadinessStatus.AT_RISK
    assert "0 IEV rows" in detail


def test_early_fetch_exactly_at_the_minimum_is_ok():
    verdict, _ = classify_early_fetch(
        is_due=True, row_count=1, minimum_rows=1, due_at_label="08:48"
    )
    assert verdict is PreOpenReadinessStatus.OK


# --------------------------------------------------------------------------
# Use case — wiring, eligibility, and refusal to guess
# --------------------------------------------------------------------------


def test_healthy_lane_at_preflight_time_is_on_track():
    response = _use_case().execute(PreOpenLaneReadinessRequest(as_of=_PREFLIGHT_AT))

    assert response.eligibility is SessionEligibility.TRADING_SESSION
    assert response.session_date == _SESSION
    assert response.on_track
    assert _row(response, PreOpenReadinessCheck.SESSION_TOKEN).status is PreOpenReadinessStatus.OK
    assert _row(response, PreOpenReadinessCheck.EARLY_FETCH).status is (
        PreOpenReadinessStatus.NOT_DUE
    )


def test_the_iev_store_is_not_read_before_the_fetch_is_due():
    """Reading at 08:41 would report `0 rows` for a fetch not yet scheduled.

    Literally true, and a false alarm — which is the failure mode that trains an
    operator to ignore the alarm entirely.
    """
    iev = _FakeIev({_SESSION: 61})
    _use_case(iev=iev).execute(PreOpenLaneReadinessRequest(as_of=_PREFLIGHT_AT))
    assert iev.calls == []


def test_missing_data_at_verify_time_raises_the_alarm():
    iev = _FakeIev({})
    response = _use_case(iev=iev).execute(PreOpenLaneReadinessRequest(as_of=_VERIFY_AT))

    assert iev.calls == [_SESSION]
    assert not response.on_track
    at_risk = response.at_risk
    assert len(at_risk) == 1
    assert at_risk[0].check is PreOpenReadinessCheck.EARLY_FETCH
    assert at_risk[0].remediation is not None


def test_a_holiday_reports_no_rows_and_does_not_alarm():
    response = _use_case().execute(
        PreOpenLaneReadinessRequest(
            as_of=datetime(2026, 8, 17, 8, 41, tzinfo=IDX_TIMEZONE),
            session_date=_HOLIDAY,
        )
    )

    assert response.eligibility is SessionEligibility.NOT_A_TRADING_SESSION
    assert response.rows == ()
    assert response.on_track


def test_an_unattested_date_still_runs_the_checks():
    """No calendar authority must never behave like a holiday.

    A stale calendar would otherwise silence the alarm on the one lane whose
    losses are permanent — failing open exactly where it is least affordable.
    """
    calendar = _FakeCalendar(
        [
            _snapshot(
                coverage_start=date(2026, 7, 1),
                coverage_end=date(2026, 7, 31),
                sessions=(date(2026, 7, 30), date(2026, 7, 31)),
            )
        ]
    )
    response = _use_case(calendar=calendar, iev=_FakeIev({})).execute(
        PreOpenLaneReadinessRequest(as_of=_VERIFY_AT)
    )

    assert response.eligibility is SessionEligibility.NO_CALENDAR_AUTHORITY
    assert len(response.rows) == 2
    assert not response.on_track


def test_an_unreadable_session_status_is_unknown_not_ok():
    def _boom() -> StockbitSessionStatus:
        raise RuntimeError("profile directory vanished")

    response = _use_case(status=_boom).execute(PreOpenLaneReadinessRequest(as_of=_PREFLIGHT_AT))

    row = _row(response, PreOpenReadinessCheck.SESSION_TOKEN)
    assert row.status is PreOpenReadinessStatus.UNKNOWN
    assert "profile directory vanished" in row.detail
    assert not response.on_track


def test_an_unreadable_iev_store_is_unknown_not_ok():
    response = _use_case(iev=_FakeIev({}, raises=True)).execute(
        PreOpenLaneReadinessRequest(as_of=_VERIFY_AT)
    )

    row = _row(response, PreOpenReadinessCheck.EARLY_FETCH)
    assert row.status is PreOpenReadinessStatus.UNKNOWN
    assert "database is locked" in row.detail
    assert not response.on_track


def test_a_naive_as_of_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        _use_case().execute(PreOpenLaneReadinessRequest(as_of=datetime(2026, 8, 13, 8, 41)))


def test_utc_input_resolves_to_the_idx_session_date():
    """01:41Z is 08:41 WIB the same day — the session must not shift."""
    response = _use_case().execute(
        PreOpenLaneReadinessRequest(as_of=datetime(2026, 8, 13, 1, 41, tzinfo=timezone.utc))
    )
    assert response.session_date == _SESSION
    assert response.on_track


def test_token_margin_is_honoured_past_the_window_close():
    """A token dying at 08:59 does not survive an 08:58 window plus margin."""
    # 08:41 -> deadline 08:58 + 10 min margin = 09:08, i.e. 1,620s required.
    response = _use_case(status=lambda: _status(seconds_remaining=1_080)).execute(
        PreOpenLaneReadinessRequest(as_of=_PREFLIGHT_AT, token_margin_minutes=10)
    )
    assert _row(response, PreOpenReadinessCheck.SESSION_TOKEN).status is (
        PreOpenReadinessStatus.AT_RISK
    )


def test_a_custom_window_and_due_time_are_respected():
    response = _use_case(iev=_FakeIev({})).execute(
        PreOpenLaneReadinessRequest(
            as_of=_PREFLIGHT_AT,
            early_fetch_due_at=time(8, 30),
            ncp_window_end=time(9, 30),
        )
    )
    # The fetch is now overdue at 08:41, so the check runs and fails.
    assert _row(response, PreOpenReadinessCheck.EARLY_FETCH).status is (
        PreOpenReadinessStatus.AT_RISK
    )
