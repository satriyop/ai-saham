"""Tests for `saham audit data manifest` / `source-contracts` / `reconcile-sources` /
`contract-gate` (DQ-000, DQ-001A, DQ-001B, DQ-001C, DQ-001D, DQ-CONTRACT-GATE)."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.application.use_case.audit_source_field_contracts_use_case import (
    AuditSourceFieldContractsResponse,
)
from src.application.use_case.audit_source_reconciliation_use_case import (
    AuditSourceReconciliationResponse,
)

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


# ── audit data contract-gate ──────────────────────────────────────────────


def _patch_both_audits_to(monkeypatch, status: str) -> None:
    """Force both underlying audits to report `status`, regardless of what
    the (possibly minimal) temp database actually contains — makes the gate's
    PASS/FAIL branch deterministic for CLI-level exit-code assertions."""
    import src.adapters.cli.audit_commands as audit_commands_module

    def fake_contracts_execute(self):
        return AuditSourceFieldContractsResponse(
            artifact_type="source_field_contract_audit",
            schema_version=1,
            generated_at="2026-07-16T00:00:00+00:00",
            tables=(),
            findings=(),
            status=status,
        )

    def fake_reconciliation_execute(self):
        return AuditSourceReconciliationResponse(
            artifact_type="source_reconciliation_audit",
            schema_version=1,
            generated_at="2026-07-16T00:00:00+00:00",
            status=status,
            checks=(),
            findings=(),
        )

    monkeypatch.setattr(
        audit_commands_module.AuditSourceFieldContractsUseCase,
        "execute",
        fake_contracts_execute,
    )
    monkeypatch.setattr(
        audit_commands_module.AuditSourceReconciliationUseCase,
        "execute",
        fake_reconciliation_execute,
    )


def test_contract_gate_json_exits_zero_on_pass(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "gate_pass.db"
    _build_temp_db(db_path)
    _patch_both_audits_to(monkeypatch, "PASS")

    result = runner.invoke(
        app,
        ["audit", "data", "contract-gate", "--format", "json", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["blockers"] == []


def test_contract_gate_json_output_has_required_top_level_fields(tmp_path: Path):
    db_path = tmp_path / "gate.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "contract-gate", "--format", "json", "--db", str(db_path)],
    )

    payload = json.loads(result.output)
    assert payload["artifact_type"] == "dq_contract_gate"
    assert payload["schema_version"] == 1
    assert payload["status"] in ("PASS", "FAIL")
    assert payload["source_contract_status"] in ("PASS", "WARN", "FAIL")
    assert payload["source_reconciliation_status"] in ("PASS", "WARN", "FAIL")
    assert isinstance(payload["blockers"], list)
    assert "generated_at" in payload


def test_contract_gate_json_exits_one_on_fail(tmp_path: Path, monkeypatch):
    """Force a FAIL by pointing --db at a nonexistent database — both
    underlying audits report FAIL (DATABASE_MISSING / MISSING_TABLE-style),
    so the gate must exit 1."""
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        ["audit", "data", "contract-gate", "--format", "json", "--db", str(missing_db)],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert len(payload["blockers"]) > 0


def test_contract_gate_table_format_exits_one_on_fail_and_shows_blockers(tmp_path: Path):
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        ["audit", "data", "contract-gate", "--db", str(missing_db)],
    )

    assert result.exit_code == 1, result.output
    assert "DQ Contract Gate" in result.output
    assert "Blockers" in result.output


def test_contract_gate_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "gate.db"
    _build_temp_db(db_path)

    result = runner.invoke(
        app,
        ["audit", "data", "contract-gate", "--format", "xml", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_contract_gate_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "gate.db"
    _build_temp_db(db_path)
    mtime_before = db_path.stat().st_mtime_ns

    runner.invoke(
        app,
        ["audit", "data", "contract-gate", "--format", "json", "--db", str(db_path)],
    )

    assert db_path.stat().st_mtime_ns == mtime_before


# ── audit data seasonality-cleanup-plan ──────────────────────────────────


def _build_seasonality_db(db_path: Path, *, with_invalid_row: bool) -> None:
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider

    StockbitSeasonalityProvider(api_client=None, db_path=db_path)  # builds schema

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO seasonality_cache
                (ticker, year, month, avg_return_pct, win_rate_pct,
                 positive_years, total_years, back_years, source, fetched_month, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("BBCA", 2026, 1, 1.0, 60.0, 3, 5, 5, "stockbit", "2026-01", "2026-01-01T00:00:00"),
        )
        if with_invalid_row:
            conn.execute(
                """
                INSERT INTO seasonality_cache
                    (ticker, year, month, avg_return_pct, win_rate_pct,
                     positive_years, total_years, back_years, source, fetched_month, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("BBRI", 2026, 2, None, None, None, None, None, None, "2026-02", None),
            )


def test_seasonality_cleanup_plan_json_output_follows_contract_when_clean(tmp_path: Path):
    db_path = tmp_path / "seasonality_clean.db"
    _build_seasonality_db(db_path, with_invalid_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifact_type"] == "seasonality_cleanup_plan"
    assert payload["schema_version"] == 1
    assert payload["table"] == "seasonality_cache"
    assert payload["status"] == "PASS"
    assert payload["source_available"] is True
    assert payload["source_unavailable_reason"] is None
    assert payload["invalid_row_count"] == 0
    assert payload["dry_run"] is True
    assert payload["proposed_action"] == "DELETE_INVALID_SEASONALITY_ROW"
    assert payload["rows"] == []


def test_seasonality_cleanup_plan_json_output_lists_invalid_rows(tmp_path: Path):
    db_path = tmp_path / "seasonality_invalid.db"
    _build_seasonality_db(db_path, with_invalid_row=True)

    result = runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["invalid_row_count"] == 1
    row = payload["rows"][0]
    assert row["ticker"] == "BBRI"
    assert set(row["reasons"]) == {"INVALID_SOURCE", "MISSING_FETCHED_AT", "ALL_METRICS_NULL"}
    assert "invalid_reason_counts" in payload
    assert payload["invalid_reason_counts"]["INVALID_SOURCE"] == 1


def test_seasonality_cleanup_plan_exits_zero_even_when_status_fail(tmp_path: Path):
    """Report command, not a gate: exit code must stay 0 regardless of status."""
    db_path = tmp_path / "seasonality_invalid.db"
    _build_seasonality_db(db_path, with_invalid_row=True)

    result = runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "FAIL"


def test_seasonality_cleanup_plan_table_format_shows_counts_and_exits_zero(tmp_path: Path):
    db_path = tmp_path / "seasonality_invalid.db"
    _build_seasonality_db(db_path, with_invalid_row=True)

    result = runner.invoke(
        app,
        ["audit", "data", "seasonality-cleanup-plan", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Seasonality Cleanup Plan" in result.output
    assert "Invalid rows: 1" in result.output
    assert "INVALID_SOURCE" in result.output


def test_seasonality_cleanup_plan_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "seasonality.db"
    _build_seasonality_db(db_path, with_invalid_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "xml", "--db", str(db_path),
        ],
    )

    assert result.exit_code != 0


def test_seasonality_cleanup_plan_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "seasonality_invalid.db"
    _build_seasonality_db(db_path, with_invalid_row=True)
    mtime_before = db_path.stat().st_mtime_ns

    runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert db_path.stat().st_mtime_ns == mtime_before


def test_seasonality_cleanup_plan_reports_fail_not_pass_for_missing_database(tmp_path: Path):
    """A wrong/missing --db must never report status PASS — that would look
    identical to "checked and found no invalid rows" — and must be
    distinguishable from a missing table via a distinct reason code."""
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "json", "--db", str(missing_db),
        ],
    )

    assert result.exit_code == 0, result.output  # still a report, not a gate
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "DATABASE_MISSING"
    assert payload["invalid_reason_counts"]["DATABASE_MISSING"] == 1
    assert payload["invalid_reason_counts"]["SEASONALITY_CACHE_TABLE_MISSING"] == 0


def test_seasonality_cleanup_plan_reports_table_missing_reason(tmp_path: Path):
    """Database exists but seasonality_cache table itself is missing — must
    use a distinct reason code from a missing database file."""
    db_path = tmp_path / "no_seasonality_table.db"
    sqlite3.connect(str(db_path)).close()  # file exists, no tables at all

    result = runner.invoke(
        app,
        [
            "audit", "data", "seasonality-cleanup-plan",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "SEASONALITY_CACHE_TABLE_MISSING"
    assert payload["invalid_reason_counts"]["SEASONALITY_CACHE_TABLE_MISSING"] == 1
    assert payload["invalid_reason_counts"]["DATABASE_MISSING"] == 0


def test_seasonality_cleanup_plan_table_format_warns_when_source_unavailable(tmp_path: Path):
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        ["audit", "data", "seasonality-cleanup-plan", "--db", str(missing_db)],
    )

    assert result.exit_code == 0, result.output
    assert "unavailable" in result.output.lower()
    assert "DATABASE_MISSING" in result.output


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


def test_dq_contract_gate_added_exactly_one_new_command():
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
    assert set(listed_commands) == {
        "manifest",
        "source-contracts",
        "reconcile-sources",
        "contract-gate",
        "seasonality-cleanup-plan",
        "repair-seasonality-cache",
    }
    assert "reconcile-sources" in result.output


# ── audit data repair-seasonality-cache ──────────────────────────────────────


def test_repair_seasonality_cache_dry_run_json_exits_zero(tmp_path: Path):
    db_path = tmp_path / "repair_seasonality.db"
    _build_seasonality_db(db_path, with_invalid_row=True)
    mtime_before = db_path.stat().st_mtime_ns

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--dry-run", "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifact_type"] == "seasonality_cache_repair"
    assert payload["mode"] == "DRY_RUN"
    assert payload["dry_run"] is True
    assert payload["status"] == "FAIL"
    assert payload["invalid_row_count"] == 1
    assert payload["quarantined_row_count"] == 0
    assert payload["deleted_row_count"] == 0
    # Ensure no mutation
    assert db_path.stat().st_mtime_ns == mtime_before


def test_repair_seasonality_cache_default_is_dry_run(tmp_path: Path):
    db_path = tmp_path / "repair_seasonality_default.db"
    _build_seasonality_db(db_path, with_invalid_row=True)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "DRY_RUN"
    assert payload["dry_run"] is True


def test_repair_seasonality_cache_dry_run_and_apply_together_fails(tmp_path: Path):
    db_path = tmp_path / "repair_seasonality_fail.db"
    _build_seasonality_db(db_path, with_invalid_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--dry-run", "--apply", "--db", str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert "Cannot use both" in result.output


def test_repair_seasonality_cache_apply_json_mutates(tmp_path: Path):
    """Apply should quarantine invalid rows and delete them from source."""
    db_path = tmp_path / "repair_apply.db"
    _build_seasonality_db(db_path, with_invalid_row=True)

    # Verify invalid row exists before
    with sqlite3.connect(str(db_path)) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache WHERE source IS NULL"
        ).fetchone()[0]
    assert before == 1

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--apply", "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "APPLY"
    assert payload["dry_run"] is False
    assert payload["invalid_row_count"] == 1
    assert payload["quarantined_row_count"] == 1
    assert payload["deleted_row_count"] == 1

    # Verify invalid row deleted from seasonality_cache
    with sqlite3.connect(str(db_path)) as conn:
        after_invalid = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache WHERE source IS NULL"
        ).fetchone()[0]
    assert after_invalid == 0

    # Verify valid row still present
    with sqlite3.connect(str(db_path)) as conn:
        after_valid = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache WHERE ticker='BBCA'"
        ).fetchone()[0]
    assert after_valid == 1

    # Verify quarantine table has the row
    with sqlite3.connect(str(db_path)) as conn:
        quarantine_count = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache_quarantine"
        ).fetchone()[0]
    assert quarantine_count == 1


def test_repair_seasonality_cache_missing_db_exits_zero_with_fail(tmp_path: Path):
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--format", "json", "--db", str(missing_db),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "DATABASE_MISSING"


def test_repair_seasonality_cache_table_format_shows_counts(tmp_path: Path):
    db_path = tmp_path / "repair_table.db"
    _build_seasonality_db(db_path, with_invalid_row=True)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--dry-run", "--format", "table", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Repair" in result.output
    assert "Invalid rows: 1" in result.output
    assert "INVALID_SOURCE" in result.output


def test_repair_seasonality_cache_clean_db_returns_pass(tmp_path: Path):
    """No invalid rows should produce PASS status."""
    db_path = tmp_path / "repair_clean.db"
    _build_seasonality_db(db_path, with_invalid_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["invalid_row_count"] == 0


def test_repair_seasonality_cache_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "repair_format.db"
    _build_seasonality_db(db_path, with_invalid_row=False)

    result = runner.invoke(
        app,
        [
            "audit", "data", "repair-seasonality-cache",
            "--format", "xml", "--db", str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert "BadParameter" in str(result.exception) or "must be one of" in result.output


# ── DQ-001I candidate_observation_identity tests ────────────────────────────


def _build_candidate_observation_db(db_path: Path) -> None:
    """Create candidate_observations table with mixed legacy/canonical rows."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE candidate_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            workflow TEXT NOT NULL DEFAULT '',
            window_sessions INTEGER NOT NULL DEFAULT 0,
            data_as_of_date TEXT NOT NULL DEFAULT '',
            config_hash TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, "
        "workflow, window_sessions, data_as_of_date, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BBCA", "2026-07-15", "2026-07-15T00:00:00+00:00", 1,
         '{"schema_version":1}', "accumulation_screen", 30, "2026-07-15", "abc123"),
    )
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, "
        "workflow, window_sessions, data_as_of_date, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BBRI", "2026-07-15", "2026-07-15T01:00:00+00:00", 1,
         '{"schema_version":1}', "accumulation_screen", 30, "2026-07-15", "def456"),
    )
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, "
        "workflow, window_sessions, data_as_of_date, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("TLKM", "2026-07-14", "2026-07-14T00:00:00+00:00", 1,
         '{"schema_version":1}', "accumulation_screen", 7, "2026-07-14", ""),
    )
    conn.commit()
    conn.close()


def test_candidate_observation_identity_command_registered():
    result = runner.invoke(app, ["audit", "data", "--help"])
    assert result.exit_code == 0, result.output
    assert "candidate-observation-identity" in result.output


def test_candidate_observation_identity_json_output_follows_contract(tmp_path: Path):
    db_path = tmp_path / "co_identity.db"
    _build_candidate_observation_db(db_path)

    result = runner.invoke(
        app,
        [
            "audit", "data", "candidate-observation-identity",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifact_type"] == "candidate_observation_identity_audit"
    assert payload["schema_version"] == 1
    assert payload["table"] == "candidate_observations"
    assert payload["status"] == "WARN"
    assert payload["source_available"] is True
    assert payload["source_unavailable_reason"] is None
    assert payload["total_row_count"] == 3
    assert payload["canonical_row_count"] == 2
    assert payload["legacy_row_count"] == 1
    assert isinstance(payload["legacy_ratio"], float)
    assert payload["snapshot_date_min"] == "2026-07-14"
    assert payload["snapshot_date_max"] == "2026-07-15"
    assert payload["captured_at_min"] is not None
    assert payload["captured_at_max"] is not None
    assert isinstance(payload["missing_identity_counts"], dict)
    assert isinstance(payload["workflow_counts"], list)
    assert isinstance(payload["window_session_counts"], list)
    assert isinstance(payload["legacy_by_snapshot_date"], list)
    assert isinstance(payload["duplicate_identity_group_count"], int)
    assert isinstance(payload["duplicate_identity_row_count"], int)
    assert isinstance(payload["latest_readiness_dependency"], dict)
    assert payload["recommendation"] == "QUARANTINE_SAFE"
    assert isinstance(payload["findings"], list)


def test_candidate_observation_identity_missing_db_returns_fail(tmp_path: Path):
    missing_db = tmp_path / "does_not_exist.db"

    result = runner.invoke(
        app,
        [
            "audit", "data", "candidate-observation-identity",
            "--format", "json", "--db", str(missing_db),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "DATABASE_MISSING"


def test_candidate_observation_identity_missing_table_returns_fail(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    sqlite3.connect(str(db_path)).close()

    result = runner.invoke(
        app,
        [
            "audit", "data", "candidate-observation-identity",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["source_available"] is False
    assert payload["source_unavailable_reason"] == "CANDIDATE_OBSERVATIONS_TABLE_MISSING"


def test_candidate_observation_identity_table_format_shows_counts(tmp_path: Path):
    db_path = tmp_path / "co_table.db"
    _build_candidate_observation_db(db_path)

    result = runner.invoke(
        app,
        [
            "audit", "data", "candidate-observation-identity",
            "--format", "table", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Candidate Observation Identity Audit" in result.output
    assert "Total rows" in result.output
    assert "Canonical rows" in result.output
    assert "Legacy rows" in result.output
    assert "QUARANTINE_SAFE" in result.output


def test_candidate_observation_identity_rejects_invalid_format(tmp_path: Path):
    db_path = tmp_path / "co_format.db"
    _build_candidate_observation_db(db_path)

    result = runner.invoke(
        app,
        [
            "audit", "data", "candidate-observation-identity",
            "--format", "xml", "--db", str(db_path),
        ],
    )

    assert result.exit_code != 0


def test_candidate_observation_identity_legacy_latest_returns_fail(tmp_path: Path):
    db_path = tmp_path / "co_legacy_latest.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE candidate_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            workflow TEXT NOT NULL DEFAULT '',
            window_sessions INTEGER NOT NULL DEFAULT 0,
            data_as_of_date TEXT NOT NULL DEFAULT '',
            config_hash TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, "
        "workflow, window_sessions, data_as_of_date, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BBCA", "2026-07-15", "2026-07-15T00:00:00+00:00", 1,
         '{}', "accumulation_screen", 30, "2026-07-15", ""),
    )
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, "
        "workflow, window_sessions, data_as_of_date, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BBRI", "2026-07-14", "2026-07-14T00:00:00+00:00", 1,
         '{}', "swing_analysis", 7, "2026-07-14", "canonical123"),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        [
            "audit", "data", "candidate-observation-identity",
            "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "FAIL"
    assert payload["recommendation"] == "REBUILD_REQUIRED"
    assert any(
        f["code"] == "LATEST_READINESS_DEPENDS_ON_LEGACY_IDENTITY"
        for f in payload["findings"]
    )
