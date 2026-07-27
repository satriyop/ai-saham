"""Tests for the `saham inspect risk` CLI command."""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from typer.testing import CliRunner

from src.adapters.cli import inspect_risk_commands
from src.adapters.cli.main import app
from src.application.dto.assess_risk import AssessRiskResponse
from src.application.rules.exceptions import RulesFileError
from src.application.use_case.run_risk_analysis_workflow_use_case import (
    RunRiskAnalysisWorkflowResult,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment

runner = CliRunner()


def _response(gate_triggered=None) -> AssessRiskResponse:
    assessment = RiskAssessment(
        rationale=("reason one",),
        snapshot_date=date(2026, 7, 10),
        indicators=IndicatorSnapshot(
            date=date(2026, 7, 10),
            sma=Decimal("1000"),
            ema=Decimal("1010"),
            rsi=Decimal("55.5"),
        ),
        gate_triggered=gate_triggered,
        gate_confidence=80 if gate_triggered else None,
    )
    return AssessRiskResponse(
        ticker="BBCA", assessment=assessment, sma_period=20, ema_period=20, rsi_period=14
    )


class FakeWorkflow:
    """Stands in for RunRiskAnalysisWorkflowUseCase: returns a result or raises."""

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
        inspect_risk_commands, "create_run_risk_analysis_workflow", lambda db_path: workflow
    )
    return workflow


def test_risk_command_delegates_to_factory_workflow(monkeypatch):
    result = RunRiskAnalysisWorkflowResult(
        ticker="BBCA", response=_response(), sentiment_snapshot=None, trend_response=None
    )
    workflow = _patch_workflow(monkeypatch, result)

    res = runner.invoke(app, ["inspect", "risk", "BBCA"])

    assert res.exit_code == 0
    assert len(workflow.requests) == 1
    assert workflow.requests[0].ticker == "BBCA"


def test_risk_command_json_format_preserves_schema(monkeypatch):
    response = _response(gate_triggered="LiquidityGate")
    result = RunRiskAnalysisWorkflowResult(
        ticker="BBCA", response=response, sentiment_snapshot=None, trend_response=None
    )
    _patch_workflow(monkeypatch, result)

    res = runner.invoke(app, ["inspect", "risk", "BBCA", "--format", "json"])

    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload == {
        "schema_version": 1,
        "artifact_type": "risk_assessment",
        "ticker": "BBCA",
        "risk_status": "BLOCKED",
        "status": "BLOCKED",
        "verdict": "BLOCKED",
        "gate_triggered": "LiquidityGate",
        "gate_confidence": 80,
        "rationale": ["reason one"],
        "indicators": {"sma_20": 1000.0, "ema_20": 1010.0, "rsi_14": 55.5},
    }


def test_risk_command_no_data_error_mapping(monkeypatch):
    _patch_workflow(monkeypatch, RuntimeError("no such table: candles"))

    res = runner.invoke(app, ["inspect", "risk", "BBCA"])

    assert res.exit_code == 1
    assert "No cached data for BBCA" in res.output


def test_risk_command_rules_file_error_mapping(monkeypatch):
    _patch_workflow(monkeypatch, RulesFileError("bad rules file"))

    res = runner.invoke(app, ["inspect", "risk", "BBCA", "--rules-file", "x.yaml"])

    assert res.exit_code == 1
    assert "[error] bad rules file" in res.output


def test_risk_command_prints_warning_from_workflow(monkeypatch):
    result = RunRiskAnalysisWorkflowResult(
        ticker="BBCA",
        response=_response(),
        sentiment_snapshot=None,
        trend_response=None,
        warnings=("Warning: Could not fetch sentiment: boom",),
    )
    _patch_workflow(monkeypatch, result)

    res = runner.invoke(app, ["inspect", "risk", "BBCA", "--with-sentiment"])

    assert res.exit_code == 0
    assert "Warning: Could not fetch sentiment: boom" in res.output


def test_risk_command_calls_display_in_table_mode(monkeypatch):
    response = _response()
    result = RunRiskAnalysisWorkflowResult(
        ticker="BBCA", response=response, sentiment_snapshot=None, trend_response=None
    )
    _patch_workflow(monkeypatch, result)
    mock_render = MagicMock()
    monkeypatch.setattr(inspect_risk_commands.display, "render_risk_assessment_table", mock_render)

    res = runner.invoke(app, ["inspect", "risk", "BBCA"])

    assert res.exit_code == 0
    mock_render.assert_called_once_with(response)
