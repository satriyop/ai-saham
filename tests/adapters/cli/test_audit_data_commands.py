"""Tests for `saham audit data manifest` / `saham audit data source-contracts` (DQ-000, DQ-001A)."""

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


# ── audit data manifest ──────────────────────────────────────────────────


def test_manifest_json_output_has_required_top_level_fields(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "manifest", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["artifact_type"] == "audit_baseline_manifest"
    assert payload["schema_version"] == 1
    assert payload["database"]["path"] == str(db_path)
    assert payload["database"]["exists"] is True
    candles_summary = next(t for t in payload["table_summaries"] if t["table"] == "candles")
    assert candles_summary["row_count"] == 1


def test_manifest_table_format_prints_summary_without_error(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(app, ["audit", "data", "manifest", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Audit Baseline Manifest" in result.output


def test_manifest_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "manifest", "--format", "xml", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_manifest_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    _build_temp_db(db_path)
    mtime_before = db_path.stat().st_mtime_ns

    result = runner.invoke(
        app,
        ["audit", "data", "manifest", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert db_path.stat().st_mtime_ns == mtime_before


# ── audit data source-contracts ──────────────────────────────────────────


def test_source_contracts_json_output_has_required_top_level_fields(tmp_path: Path):
    db_path = tmp_path / "source_contracts.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "source-contracts", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["artifact_type"] == "source_field_contract_audit"
    assert payload["schema_version"] == 1
    assert payload["status"] in ("PASS", "WARN", "FAIL")
    candles = next(t for t in payload["tables"] if t["table"] == "candles")
    assert candles["exists"] is True
    assert candles["row_count"] == 1


def test_source_contracts_table_format_prints_summary_without_error(tmp_path: Path):
    db_path = tmp_path / "source_contracts.db"
    _build_temp_db(db_path)

    result = runner.invoke(app, ["audit", "data", "source-contracts", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Source Field Contract Audit" in result.output


def test_source_contracts_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "source_contracts.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "source-contracts", "--format", "xml", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_source_contracts_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "source_contracts.db"
    _build_temp_db(db_path)
    mtime_before = db_path.stat().st_mtime_ns

    result = runner.invoke(
        app,
        ["audit", "data", "source-contracts", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert db_path.stat().st_mtime_ns == mtime_before


# ── registration ──────────────────────────────────────────────────────────


def test_audit_is_registered_as_top_level_command():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "audit" in result.output


def test_audit_data_exposes_manifest_and_source_contracts():
    result = runner.invoke(app, ["audit", "data", "--help"])

    assert result.exit_code == 0
    assert "manifest" in result.output
    assert "source-contracts" in result.output
