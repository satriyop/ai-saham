"""Tests for `saham audit data repair-signal-forward-labels` (DQ-001L)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def _build_test_db(
    db_path: Path,
    *,
    with_orphan_row: bool,
) -> None:
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteSignalForwardLabelsRepository(db_path)
    SQLiteCandidateObservationsRepository(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("BBCA", "2026-07-15", "2026-07-15T00:00:00", 1, "{}", "hash1"),
    )
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, "
        "outcome_label, fingerprint_json, schema_version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "BBCA", "2026-07-15", "SHORT", "2026-07-15T00:00:00",
            "UP", '{"v":1}', 1, "2026-07-16T00:00:00", "2026-07-16T00:00:00",
        ),
    )
    if with_orphan_row:
        conn.execute(
            "INSERT INTO signal_forward_labels "
            "(ticker, signal_date, horizon, observation_captured_at, "
            "outcome_label, fingerprint_json, schema_version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "BBRI", "2026-07-14", "SHORT", "2026-07-14T00:00:00",
                "UP", '{"v":1}', 1, "2026-07-16T00:00:00", "2026-07-16T00:00:00",
            ),
        )
    conn.commit()
    conn.close()


# ── command registration ─────────────────────────────────────────────────────


def test_command_registered_under_audit_data():
    result = runner.invoke(app, ["audit", "data", "--help"])

    assert result.exit_code == 0, result.output
    assert "repair-signal-forward-labels" in result.output


# ── dry-run / default mode ───────────────────────────────────────────────────


def test_default_mode_is_dry_run(tmp_path: Path):
    db_path = tmp_path / "repair_default.db"
    _build_test_db(db_path, with_orphan_row=True)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "DRY_RUN"
    assert payload["dry_run"] is True


def test_dry_run_json_exits_zero_and_does_not_mutate(tmp_path: Path):
    db_path = tmp_path / "repair_dry_run.db"
    _build_test_db(db_path, with_orphan_row=True)
    mtime_before = db_path.stat().st_mtime_ns

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--dry-run", "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifact_type"] == "signal_forward_labels_repair"
    assert payload["mode"] == "DRY_RUN"
    assert payload["status"] == "FAIL"
    assert payload["orphan_row_count"] == 1
    assert payload["quarantined_row_count"] == 0
    assert payload["deleted_row_count"] == 0
    assert db_path.stat().st_mtime_ns == mtime_before


# ── apply ─────────────────────────────────────────────────────────────────────


def test_apply_json_mutates_and_exits_zero(tmp_path: Path):
    db_path = tmp_path / "repair_apply.db"
    _build_test_db(db_path, with_orphan_row=True)

    with sqlite3.connect(str(db_path)) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels"
        ).fetchone()[0]
    assert before == 2

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--apply", "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "APPLY"
    assert payload["dry_run"] is False
    assert payload["status"] == "PASS"
    assert payload["orphan_row_count"] == 1
    assert payload["quarantined_row_count"] == 1
    assert payload["deleted_row_count"] == 1

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT ticker FROM signal_forward_labels ORDER BY ticker"
        ).fetchall()
    assert [r[0] for r in remaining] == ["BBCA"]

    with sqlite3.connect(str(db_path)) as conn:
        qc = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels_quarantine"
        ).fetchone()[0]
    assert qc == 1


def test_second_apply_reports_zero_orphan_rows(tmp_path: Path):
    db_path = tmp_path / "repair_apply_twice.db"
    _build_test_db(db_path, with_orphan_row=True)

    runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--apply", "--format", "json", "--db", str(db_path),
        ],
    )
    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--apply", "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["orphan_row_count"] == 0
    assert payload["quarantined_row_count"] == 0

    with sqlite3.connect(str(db_path)) as conn:
        qc = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels_quarantine"
        ).fetchone()[0]
    assert qc == 1


# ── invalid flag combinations ─────────────────────────────────────────────────


def test_dry_run_and_apply_together_fails(tmp_path: Path):
    db_path = tmp_path / "repair_conflict.db"
    _build_test_db(db_path, with_orphan_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--dry-run", "--apply", "--db", str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert "Cannot use both" in result.output


def test_invalid_format_fails(tmp_path: Path):
    db_path = tmp_path / "repair_bad_format.db"
    _build_test_db(db_path, with_orphan_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--format", "xml", "--db", str(db_path),
        ],
    )

    assert result.exit_code != 0


# ── source unavailable ────────────────────────────────────────────────────────


def test_missing_db_exits_zero_with_fail(tmp_path: Path):
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--format", "json", "--db", str(missing_db),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "DATABASE_MISSING"


def test_missing_candidate_observations_exits_zero_with_fail(tmp_path: Path):
    db_path = tmp_path / "no_co_table.db"
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    SQLiteSignalForwardLabelsRepository(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, "
        "outcome_label, fingerprint_json, schema_version, created_at, updated_at) "
        "VALUES ('BBCA', '2026-07-15', 'SHORT', '2026-07-15T00:00:00', "
        "'UP', '{\"v\":1}', 1, '2026-07-16T00:00:00', '2026-07-16T00:00:00')"
    )
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "CANDIDATE_OBSERVATIONS_TABLE_MISSING"


# ── table output ─────────────────────────────────────────────────────────────


def test_table_output_includes_key_counts(tmp_path: Path):
    db_path = tmp_path / "repair_table.db"
    _build_test_db(db_path, with_orphan_row=True)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-signal-forward-labels",
            "--dry-run", "--format", "table", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Signal Forward Labels Repair" in result.output
    assert "Orphan rows" in result.output
    assert "Dry-run" in result.output or "Dry run" in result.output
