"""Tests for the `saham analyze accum-audit` CLI command."""

import json
from datetime import date

from typer.testing import CliRunner

from src.adapters.cli import analyze_accum_commands
from src.adapters.cli.analyze_commands import analyze_app
from src.application.dto.accumulation_audit import AccumulationAuditResponse
from src.application.use_case.run_accumulation_audit_workflow_use_case import (
    NoTickersError,
    RunAccumulationAuditWorkflowResult,
)

runner = CliRunner()


def _response(**overrides) -> AccumulationAuditResponse:
    defaults = dict(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
        window_days=7,
        total_replay_dates=1,
        total_tickers=1,
        total_records=0,
        skipped_no_forward_data=0,
        records=[],
        group_stats=[],
        exit_simulations=[],
        warnings=[],
    )
    defaults.update(overrides)
    return AccumulationAuditResponse(**defaults)


def _result(response=None, **overrides) -> RunAccumulationAuditWorkflowResult:
    response = response or _response()
    defaults = dict(
        response=response,
        ticker_count=1,
        start_date=response.start_date,
        end_date=response.end_date,
        window=response.window_days,
        min_foreign_flow_score=40.0,
        filter_label="",
        resolved_tickers=("BBCA",),
    )
    defaults.update(overrides)
    return RunAccumulationAuditWorkflowResult(**defaults)


class FakeWorkflow:
    """Stands in for RunAccumulationAuditWorkflowUseCase: returns a result or raises."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _patch_workflow(monkeypatch, outcome) -> FakeWorkflow:
    workflow = FakeWorkflow(outcome)
    monkeypatch.setattr(
        analyze_accum_commands,
        "create_run_accumulation_audit_workflow",
        lambda *, db_path: workflow,
    )
    return workflow


def test_command_delegates_to_workflow_factory(monkeypatch):
    workflow = _patch_workflow(monkeypatch, _result())

    res = runner.invoke(analyze_app, ["accum-audit", "BBCA"])

    assert res.exit_code == 0
    assert len(workflow.requests) == 1


def test_request_dto_contains_raw_cli_intent_not_resolved_setup_values(monkeypatch):
    workflow = _patch_workflow(monkeypatch, _result())

    res = runner.invoke(
        analyze_app, ["accum-audit", "BBCA", "--setup", "foreign-bounce"]
    )

    assert res.exit_code == 0
    sent = workflow.requests[0]
    assert sent.setup == "foreign-bounce"
    assert sent.tickers == ["BBCA"]
    assert sent.window is None
    assert sent.min_foreign_flow_score is None


def test_json_mode_prints_result_to_json_dict(monkeypatch):
    response = _response(warnings=["heads up"])
    _patch_workflow(monkeypatch, _result(response=response))

    res = runner.invoke(analyze_app, ["accum-audit", "BBCA", "--format", "json"])

    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["schema_version"] == 2
    assert payload["artifact_type"] == "accumulation_audit"
    assert payload["start_date"] == "2026-01-01"
    assert payload["end_date"] == "2026-01-10"
    assert payload["window_days"] == 7
    assert payload["total_replay_dates"] == 1
    assert payload["total_tickers"] == 1
    assert payload["total_records"] == 0
    assert payload["skipped_no_forward_data"] == 0
    assert payload["warnings"] == ["heads up"]
    assert payload["group_stats"] == []
    assert payload["exit_simulations"] == []
    assert "skip_ledger" in payload
    assert payload["claim_stamp"]["evaluation_role"] == "DESCRIPTIVE"
    assert payload["claim_stamp"]["outcome_basis"] == "raw_market"
    assert payload["claim_stamp"]["costs_modeled"] is False
    assert payload["records_in_json"] is False


def test_json_mode_does_not_write_signal_tables(monkeypatch, tmp_path):
    """DQ-011 D11-6: accum-audit JSON path must not touch observation/label tables."""
    import sqlite3

    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    db_path = tmp_path / "accum.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)
    _patch_workflow(monkeypatch, _result())

    res = runner.invoke(
        analyze_app,
        ["accum-audit", "BBCA", "--format", "json", "--db", str(db_path)],
    )

    assert res.exit_code == 0, res.output
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_forward_labels").fetchone()[0] == 0


def test_table_mode_prints_progress_line_and_calls_display(monkeypatch):
    _patch_workflow(monkeypatch, _result(filter_label=" | filters: trend=UP"))
    called = {}

    def _fake_display(response, top_groups):
        called["top_groups"] = top_groups

    monkeypatch.setattr(
        "src.adapters.cli.analyze_accum_display.display_audit_summary", _fake_display
    )

    res = runner.invoke(analyze_app, ["accum-audit", "BBCA", "--top-groups", "5"])

    assert res.exit_code == 0
    assert "Auditing 1 tickers" in res.output
    assert "filters: trend=UP" in res.output
    assert called["top_groups"] == 5


def test_csv_output_calls_writer_and_prints_confirmation(monkeypatch, tmp_path):
    response = _response(total_records=3)
    _patch_workflow(monkeypatch, _result(response=response))
    written = {}

    def _fake_write(resp, path):
        written["response"] = resp
        written["path"] = path

    monkeypatch.setattr(analyze_accum_commands, "write_accumulation_audit_csv", _fake_write)

    output_path = tmp_path / "out.csv"
    res = runner.invoke(
        analyze_app, ["accum-audit", "BBCA", "--output", str(output_path)]
    )

    assert res.exit_code == 0
    assert written["path"] == output_path
    assert f"Wrote 3 audit records to {output_path}" in res.output


def test_json_mode_with_csv_writes_confirmation_to_stderr(monkeypatch, tmp_path):
    response = _response(total_records=2)
    _patch_workflow(monkeypatch, _result(response=response))
    monkeypatch.setattr(
        analyze_accum_commands, "write_accumulation_audit_csv", lambda resp, path: None
    )

    output_path = tmp_path / "out.csv"
    res = runner.invoke(
        analyze_app,
        ["accum-audit", "BBCA", "--output", str(output_path), "--format", "json"],
    )

    assert res.exit_code == 0
    assert f"Wrote 2 audit records to {output_path}" in res.stderr
    assert "Wrote" not in res.stdout


def test_workflow_value_error_maps_to_exit_1_with_error_prefix(monkeypatch):
    _patch_workflow(monkeypatch, ValueError("unknown setup 'x'. Available setups: a, b"))

    res = runner.invoke(analyze_app, ["accum-audit", "BBCA", "--setup", "x"])

    assert res.exit_code == 1
    assert "Error: unknown setup 'x'. Available setups: a, b" in res.output


def test_workflow_no_tickers_error_maps_to_exit_1_without_error_prefix(monkeypatch):
    _patch_workflow(
        monkeypatch,
        NoTickersError("No tickers to audit. Specify --universe or provide ticker arguments."),
    )

    res = runner.invoke(analyze_app, ["accum-audit"])

    assert res.exit_code == 1
    assert "No tickers to audit. Specify --universe or provide ticker arguments." in res.output
    assert "Error:" not in res.output
