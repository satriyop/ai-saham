"""Tests for `saham fetch audit` CLI wiring (default quality-audit behavior only).

DQ-000 manifest and DQ-001A source-field contract audits now live under
`saham audit data manifest` / `saham audit data source-contracts` — see the
sibling `test_audit_data_commands` module in this same directory.
"""

from __future__ import annotations

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


def test_quality_audit_default_behavior(tmp_path: Path):
    db_path = tmp_path / "quality_audit.db"
    _build_temp_db(db_path)

    result = runner.invoke(app, ["fetch", "audit", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Data Quality Audit" in result.output


def test_manifest_flag_no_longer_exists(tmp_path: Path):
    db_path = tmp_path / "quality_audit.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app, ["fetch", "audit", "--manifest", "--db", str(db_path)]
    )

    assert result.exit_code != 0


def test_source_contracts_flag_no_longer_exists(tmp_path: Path):
    db_path = tmp_path / "quality_audit.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app, ["fetch", "audit", "--source-contracts", "--db", str(db_path)]
    )

    assert result.exit_code != 0
