"""
CLI tests for `saham audit preopen-readiness`.

The adapter's whole job is flags in, exit code out — and the exit code is what
cron acts on, so it is the contract worth testing. 0 must mean "on track", 1
must mean bad input, and 2 must mean the lane is at risk; a checker that reports
a broken environment as a healthy lane is worse than no checker.

All fakes are in-memory. No network, no browser.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import pytest
from typer.testing import CliRunner

from src.adapters.cli.audit_commands import audit_app
from src.application.dto.preopen_lane_readiness import (
    PreOpenLaneReadinessResponse,
    PreOpenReadinessCheck,
    PreOpenReadinessRow,
    PreOpenReadinessStatus,
    SessionEligibility,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE

runner = CliRunner()

_MODULE = "src.adapters.cli.audit_preopen_readiness_commands"
_SESSION = date(2026, 8, 13)


@pytest.fixture
def db(tmp_path):
    """An existing (empty) database. `--db` fails closed and never creates one."""
    path = tmp_path / "data.db"
    sqlite3.connect(path).close()
    return path


def _response(*, on_track: bool, eligibility=SessionEligibility.TRADING_SESSION):
    status = PreOpenReadinessStatus.OK if on_track else PreOpenReadinessStatus.AT_RISK
    return PreOpenLaneReadinessResponse(
        session_date=_SESSION,
        as_of=datetime(2026, 8, 13, 8, 41, tzinfo=IDX_TIMEZONE),
        eligibility=eligibility,
        rows=(
            PreOpenReadinessRow(
                check=PreOpenReadinessCheck.SESSION_TOKEN,
                status=status,
                detail="token detail",
                remediation=None if on_track else "saham fetch stockbit reauth --mode headed",
            ),
            PreOpenReadinessRow(
                check=PreOpenReadinessCheck.EARLY_FETCH,
                status=PreOpenReadinessStatus.NOT_DUE,
                detail="not due",
            ),
        ),
        calendar_snapshot_ids=("snap-1",),
    )


@pytest.fixture
def stub_use_case(monkeypatch):
    """Replace the use case wholesale; the adapter owns no policy to test."""

    def _install(response):
        class _Fake:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def execute(self, request):
                return response

        monkeypatch.setattr(f"{_MODULE}.AssessPreOpenLaneReadinessUseCase", _Fake)

    return _install


def test_on_track_lane_exits_zero(db, stub_use_case):
    stub_use_case(_response(on_track=True))
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(db)])
    assert result.exit_code == 0
    assert "ON TRACK" in result.stdout


def test_at_risk_without_require_ready_still_exits_zero(db, stub_use_case):
    """Reporting is the default; only cron opts into a failing exit code."""
    stub_use_case(_response(on_track=False))
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(db)])
    assert result.exit_code == 0
    assert "AT RISK" in result.stdout


def test_at_risk_with_require_ready_exits_two(db, stub_use_case):
    stub_use_case(_response(on_track=False))
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(db), "--require-ready"])
    assert result.exit_code == 2
    assert "reauth --mode headed" in result.stdout


def test_holiday_hint_appears_only_without_calendar_authority(db, stub_use_case):
    stub_use_case(_response(on_track=False, eligibility=SessionEligibility.NO_CALENDAR_AUTHORITY))
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(db)])
    assert "IDX public holiday" in result.stdout


def test_json_format_is_machine_readable(db, stub_use_case):
    stub_use_case(_response(on_track=True))
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(db), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["on_track"] is True
    assert payload["session_date"] == "2026-08-13"
    assert [check["check"] for check in payload["checks"]] == [
        "SESSION_TOKEN",
        "EARLY_FETCH",
    ]


@pytest.mark.parametrize(
    "args",
    [
        ["--format", "yaml"],
        ["--session", "13-08-2026"],
        # NB: "0841" is NOT here — time.fromisoformat accepts basic ISO format.
        ["--as-of", "25:00"],
        ["--window-end", "8h58"],
        ["--min-rows", "0"],
        ["--token-margin", "-1"],
    ],
)
def test_bad_input_is_rejected(db, stub_use_case, args):
    """Click raises its own usage exit for BadParameter; the house asserts non-zero.

    The value being guarded is that a malformed flag never reaches the use case
    and never reads as "on track".
    """
    stub_use_case(_response(on_track=True))
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(db), *args])
    assert result.exit_code != 0
    assert "ON TRACK" not in result.stdout


def test_missing_db_is_a_user_error_and_is_not_created(tmp_path, stub_use_case):
    """An explicit --db must fail closed, never silently create an empty store."""
    stub_use_case(_response(on_track=True))
    absent = tmp_path / "nope.db"
    result = runner.invoke(audit_app, ["preopen-readiness", "--db", str(absent)])
    assert result.exit_code == 1
    assert not absent.exists()
