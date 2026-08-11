"""CLI-level tests for `saham audit corpus-continuity`.

Covers the operator contract the cron wrapper depends on: exit 0 when the
corpus is whole, exit 2 under `--require-healthy` when it is not, exit 0 with
no `Error:` prefix for a valid empty corpus, and exit 1 for a missing `--db`.

Runs entirely against a temp SQLite file. No network.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotRepository,
)

runner = CliRunner()

_SESSIONS = (date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10))
_COHORT = "sha256:clitestcohort"
_WIDTH = 5


def _seed(db: Path, sessions: tuple[date, ...], *, width: int = _WIDTH) -> None:
    observations = SQLiteLearningArtifactRepository(db)
    for session in sessions:
        cutoff = datetime.combine(session, datetime.min.time(), IDX_TIMEZONE).replace(hour=16)
        for index in range(width):
            observations.add_observation(
                LearningObservation.create(
                    purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
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
            )
    SQLiteTradingSessionCalendarSnapshotRepository(db).add_snapshot(
        TradingSessionCalendarSnapshot.create(
            coverage_start=_SESSIONS[0],
            coverage_end=_SESSIONS[-1],
            ordered_sessions=_SESSIONS,
            source_revision="r-cli",
            captured_at=datetime(2026, 7, 11, 19, 0, tzinfo=IDX_TIMEZONE),
        )
    )


def _invoke(db: Path, *extra: str):
    return runner.invoke(
        app,
        [
            "audit",
            "corpus-continuity",
            "--db",
            str(db),
            "--purpose",
            "accum",
            "--as-of",
            _SESSIONS[-1].isoformat(),
            *extra,
        ],
    )


def test_whole_corpus_exits_zero(tmp_path: Path) -> None:
    db = tmp_path / "whole.db"
    _seed(db, _SESSIONS)

    result = _invoke(db, "--expected-width", str(_WIDTH), "--require-healthy")

    assert result.exit_code == 0
    assert "HEALTHY" in result.stdout


def test_missing_session_fails_closed_under_require_healthy(tmp_path: Path) -> None:
    db = tmp_path / "hole.db"
    _seed(db, (_SESSIONS[0], _SESSIONS[2]))

    result = _invoke(db, "--expected-width", str(_WIDTH), "--require-healthy")

    assert result.exit_code == 2
    assert "MISSING" in result.stdout


def test_missing_session_without_require_healthy_still_exits_zero(tmp_path: Path) -> None:
    """Reporting is not alerting: the strict flag is what cron opts into."""
    db = tmp_path / "hole-soft.db"
    _seed(db, (_SESSIONS[0], _SESSIONS[2]))

    result = _invoke(db, "--expected-width", str(_WIDTH))

    assert result.exit_code == 0


def test_thin_session_is_flagged_under_covered(tmp_path: Path) -> None:
    db = tmp_path / "thin.db"
    _seed(db, _SESSIONS[:2])
    _seed_extra_session(db, _SESSIONS[2], width=1)

    result = _invoke(db, "--expected-width", str(_WIDTH), "--require-healthy")

    assert result.exit_code == 2
    assert "UNDER_COVERED" in result.stdout


def _seed_extra_session(db: Path, session: date, *, width: int) -> None:
    observations = SQLiteLearningArtifactRepository(db)
    cutoff = datetime.combine(session, datetime.min.time(), IDX_TIMEZONE).replace(hour=16)
    for index in range(width):
        observations.add_observation(
            LearningObservation.create(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
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
        )


def test_empty_corpus_is_a_valid_empty_result(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    SQLiteLearningArtifactRepository(db)
    SQLiteTradingSessionCalendarSnapshotRepository(db)

    result = _invoke(db, "--require-healthy")

    assert result.exit_code == 0
    assert "Error:" not in result.stdout
    assert "No ACCUMULATION_DISCOVERY observations" in result.stdout


def test_missing_db_is_a_user_error(tmp_path: Path) -> None:
    """Explicit --db must fail closed on exit 1, and must never create the file."""
    absent = tmp_path / "absent.db"

    result = _invoke(absent)

    assert result.exit_code == 1
    assert not absent.exists()
    assert "Error [user_input]" in (result.stderr or result.stdout)


def test_json_output_is_machine_readable(tmp_path: Path) -> None:
    db = tmp_path / "json.db"
    _seed(db, (_SESSIONS[0], _SESSIONS[2]))

    result = _invoke(db, "--expected-width", str(_WIDTH), "--format", "json")

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["missing_sessions"] == [_SESSIONS[1].isoformat()]
    assert payload["operationally_healthy"] is False
    assert payload["counts"]["MISSING"] == 1
    assert len(payload["calendar_snapshot_ids"]) == 1


def test_undeclared_width_does_not_flag_thin_sessions(tmp_path: Path) -> None:
    db = tmp_path / "nowidth.db"
    _seed(db, _SESSIONS[:2])
    _seed_extra_session(db, _SESSIONS[2], width=1)

    result = _invoke(db, "--require-healthy")

    assert result.exit_code == 0
    assert "UNDER_COVERED" not in result.stdout


def test_bad_format_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "fmt.db"
    _seed(db, _SESSIONS)

    result = _invoke(db, "--format", "yaml")

    assert result.exit_code != 0


def test_bad_min_coverage_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "cov.db"
    _seed(db, _SESSIONS)

    result = _invoke(db, "--min-coverage", "0")

    assert result.exit_code != 0
