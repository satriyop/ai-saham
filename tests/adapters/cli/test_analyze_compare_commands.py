"""Tests for the `saham analyze compare` CLI command."""

from decimal import Decimal

from typer.testing import CliRunner

from src.adapters.cli import analyze_compare_commands
from src.adapters.cli.analyze_commands import analyze_app
from src.application.use_case.run_risk_compare_use_case import (
    RiskCompareRow,
    RunRiskCompareResult,
)

runner = CliRunner()


class FakeCompareWorkflow:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _patch_workflow(monkeypatch, outcome) -> FakeCompareWorkflow:
    workflow = FakeCompareWorkflow(outcome)
    monkeypatch.setattr(
        analyze_compare_commands, "create_run_risk_compare_workflow", lambda db_path: workflow
    )
    return workflow


def test_compare_command_delegates_to_factory_workflow(monkeypatch):
    result = RunRiskCompareResult(
        rows=(
            RiskCompareRow(
                ticker="BBCA",
                close=Decimal("1050"),
                sma=Decimal("1000"),
                rsi=Decimal("55"),
                risk_level_name="OPEN",
                confidence=0,
                has_data=True,
            ),
            RiskCompareRow(
                ticker="BBRI",
                close=Decimal("2050"),
                sma=Decimal("2000"),
                rsi=Decimal("60"),
                risk_level_name="BLOCKED",
                confidence=80,
                has_data=True,
            ),
        )
    )
    workflow = _patch_workflow(monkeypatch, result)

    res = runner.invoke(analyze_app, ["compare", "BBCA", "BBRI"])

    assert res.exit_code == 0
    assert len(workflow.requests) == 1
    assert workflow.requests[0].tickers == ["BBCA", "BBRI"]
    assert "BBCA" in res.output
    assert "BBRI" in res.output


def test_compare_command_fewer_than_two_tickers_exits_with_error(monkeypatch):
    _patch_workflow(monkeypatch, ValueError("Provide at least 2 tickers to compare."))

    res = runner.invoke(analyze_app, ["compare", "BBCA"])

    assert res.exit_code != 0
    assert "Provide at least 2 tickers to compare." in res.output


def test_compare_command_renders_no_data_for_failed_row(monkeypatch):
    result = RunRiskCompareResult(
        rows=(
            RiskCompareRow(
                ticker="BBCA",
                close=Decimal("1050"),
                sma=Decimal("1000"),
                rsi=Decimal("55"),
                risk_level_name="OPEN",
                confidence=0,
                has_data=True,
            ),
            RiskCompareRow(
                ticker="XXXX",
                close=None,
                sma=None,
                rsi=None,
                risk_level_name=None,
                confidence=None,
                has_data=False,
            ),
        )
    )
    _patch_workflow(monkeypatch, result)

    res = runner.invoke(analyze_app, ["compare", "BBCA", "XXXX"])

    assert res.exit_code == 0
    assert "NO DATA" in res.output


def test_compare_command_renders_dash_close_when_assessment_succeeds_without_candles(monkeypatch):
    """Assessment can succeed with has_data=True even when the repository has no candles
    for the ticker yet (e.g. gate-only data available). Close must render as em-dash
    instead of crashing the format spec on None."""
    result = RunRiskCompareResult(
        rows=(
            RiskCompareRow(
                ticker="BBCA",
                close=Decimal("1050"),
                sma=Decimal("1000"),
                rsi=Decimal("55"),
                risk_level_name="OPEN",
                confidence=0,
                has_data=True,
            ),
            RiskCompareRow(
                ticker="BBRI",
                close=None,
                sma=Decimal("2000"),
                rsi=Decimal("60"),
                risk_level_name="BLOCKED",
                confidence=80,
                has_data=True,
            ),
        )
    )
    _patch_workflow(monkeypatch, result)

    res = runner.invoke(analyze_app, ["compare", "BBCA", "BBRI"])

    assert res.exit_code == 0
    assert "NO DATA" not in res.output
    assert "BLOCKED" in res.output
    lines = [line for line in res.output.splitlines() if line.startswith("BBRI")]
    assert len(lines) == 1
    assert "—" in lines[0]
