"""Tests for `saham audit data manifest` / `source-contracts` / `reconcile-sources`
(DQ-000, DQ-001A, DQ-001B, DQ-001C, DQ-001D)."""

from __future__ import annotations

import json
import re
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


def test_source_contracts_json_output_includes_dq_001c_enrichment_tables(tmp_path: Path):
    db_path = tmp_path / "source_contracts.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "source-contracts", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    table_names = {t["table"] for t in payload["tables"]}
    for expected in (
        "analyst_cache",
        "insider_cache",
        "company_fundamentals",
        "shareholding_composition",
        "seasonality_cache",
        "ticker_notation_cache",
        "bandar_detector",
        "corporate_action_events",
        "corporate_action_event_dates",
        "forward_estimates_cache",
        "company_profile_cache",
        "earnings_cache",
        "stock_meta",
    ):
        assert expected in table_names


def test_source_contracts_json_output_includes_dq_001e_signal_artifact_tables(tmp_path: Path):
    db_path = tmp_path / "source_contracts.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "source-contracts", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    table_names = {t["table"] for t in payload["tables"]}
    for expected in (
        "candidate_observations",
        "signal_forward_labels",
        "market_context_snapshots",
        "regime_observations",
    ):
        assert expected in table_names


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


# ── audit data reconcile-sources ─────────────────────────────────────────


def test_reconcile_sources_json_output_has_required_top_level_fields(tmp_path: Path):
    db_path = tmp_path / "reconcile.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "reconcile-sources", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["artifact_type"] == "source_reconciliation_audit"
    assert payload["schema_version"] == 1
    assert payload["status"] in ("PASS", "WARN", "FAIL")
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["findings"], list)
    candles_check = next(c for c in payload["checks"] if c["name"] == "candles_ohlc_invariants")
    assert candles_check["checked_row_count"] == 1


def test_reconcile_sources_json_output_includes_dq_001d_enrichment_findings(tmp_path: Path):
    db_path = tmp_path / "reconcile.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "reconcile-sources", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    check_names = {c["name"] for c in payload["checks"]}
    for expected in (
        "seasonality_provenance_consistency",
        "company_fundamentals_pit_coverage",
        "analyst_cache_pit_coverage",
        "insider_cache_pit_coverage",
        "corporate_action_event_linkage",
        "forward_estimates_pit_coverage",
        "ticker_notation_cache_limitation",
        "stock_meta_provenance",
    ):
        assert expected in check_names

    # _build_temp_db only creates `candles`; enrichment tables are absent so
    # they surface as explicit WARN findings rather than crashing.
    ticker_notation_findings = [
        f for f in payload["findings"] if f["table"] == "ticker_notation_cache"
    ]
    assert any(f["code"] == "MISSING_ENRICHMENT_TABLE" for f in ticker_notation_findings)


def test_reconcile_sources_json_output_includes_dq_001e_artifact_checks(tmp_path: Path):
    db_path = tmp_path / "reconcile.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "reconcile-sources", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    check_names = {c["name"] for c in payload["checks"]}
    for expected in (
        "candidate_observations_identity",
        "signal_forward_labels_identity_linkage",
        "market_context_snapshot_identity",
        "regime_observations_identity",
    ):
        assert expected in check_names

    # _build_temp_db only creates `candles`; market_context_snapshots and
    # regime_observations are absent so they surface as explicit WARN
    # findings rather than crashing. These are context/artifact tables, not
    # enrichment tables, so they use a distinct finding code.
    market_context_findings = [
        f for f in payload["findings"] if f["table"] == "market_context_snapshots"
    ]
    assert any(f["code"] == "MISSING_OPTIONAL_ARTIFACT_TABLE" for f in market_context_findings)


def test_reconcile_sources_table_format_prints_summary_without_error(tmp_path: Path):
    db_path = tmp_path / "reconcile.db"
    _build_temp_db(db_path)

    result = runner.invoke(app, ["audit", "data", "reconcile-sources", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Source Reconciliation Audit" in result.output


def test_reconcile_sources_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "reconcile.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "reconcile-sources", "--format", "xml", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_reconcile_sources_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "reconcile.db"
    _build_temp_db(db_path)
    mtime_before = db_path.stat().st_mtime_ns

    result = runner.invoke(
        app,
        ["audit", "data", "reconcile-sources", "--format", "json", "--db", str(db_path)],
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


def test_dq_001d_did_not_add_a_new_command():
    result = runner.invoke(app, ["audit", "data", "--help"])

    assert result.exit_code == 0
    listed_commands: list[str] = []
    in_commands = False
    for line in result.output.splitlines():
        if " Commands " in line:
            in_commands = True
            continue
        if in_commands and line.startswith("╰"):
            break
        if not in_commands:
            continue
        match = re.match(r"^│\s+([a-z][\w-]*)\s{2,}", line)
        if match:
            listed_commands.append(match.group(1))
    assert set(listed_commands) == {"manifest", "source-contracts", "reconcile-sources"}
    assert "reconcile-sources" in result.output
