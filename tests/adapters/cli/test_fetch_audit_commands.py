"""Tests for `saham fetch audit` CLI wiring, including --manifest (DQ-000)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def _build_temp_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE candles (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            volume INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'unknown'
        )
        """
    )
    conn.execute(
        "INSERT INTO candles (ticker, date, open, high, low, close, volume, source) "
        "VALUES ('BBCA', '2026-01-02', '1', '1', '1', '1', 1, 'idx')"
    )
    conn.commit()
    conn.close()


def test_manifest_json_output_has_required_top_level_fields(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["fetch", "audit", "--manifest", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["artifact_type"] == "audit_baseline_manifest"
    assert payload["schema_version"] == 1
    assert payload["database"]["path"] == str(db_path)
    assert payload["database"]["exists"] is True
    assert isinstance(payload["table_summaries"], list)
    candles_summary = next(t for t in payload["table_summaries"] if t["table"] == "candles")
    assert candles_summary["row_count"] == 1


def test_manifest_json_output_on_missing_database_reports_warning(tmp_path: Path):
    db_path = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        ["fetch", "audit", "--manifest", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["database"]["exists"] is False
    assert "database_missing" in payload["warnings"]


def test_manifest_table_format_prints_summary_without_error(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["fetch", "audit", "--manifest", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Audit Baseline Manifest" in result.output


def test_manifest_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["fetch", "audit", "--manifest", "--format", "xml", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_existing_quality_audit_path_is_unchanged_without_manifest_flag(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(app, ["fetch", "audit", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Data Quality Audit" in result.output
    assert "audit_baseline_manifest" not in result.output


def test_manifest_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)
    mtime_before = db_path.stat().st_mtime_ns

    result = runner.invoke(
        app,
        ["fetch", "audit", "--manifest", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert db_path.stat().st_mtime_ns == mtime_before
