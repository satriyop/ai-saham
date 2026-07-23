"""Tests for the trade accumulation CLI commands."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import src.adapters.cli.trade_accum_commands as trade_accum_cli
from src.adapters.cli.main import app
from src.application.use_case.log_accumulation_trade_workflow_use_case import (
    LogAccumulationTradeWorkflowBundle,
)
from src.application.use_case.log_swing_candidate_use_case import (
    LogSwingCandidateResponse,
)

runner = CliRunner()


class FakeWorkflow:
    def __init__(self, response, policy):
        self.response = response
        self.recorded_request = None

    def execute(self, request):
        self.recorded_request = request
        if request.from_analysis and request.setup == "invalid-setup":
            raise ValueError(
                "Unknown swing setup 'invalid-setup'. Available setups: foreign-bounce"
            )

        return SimpleNamespace(
            response=self.response,
            setup_name=request.setup.lower(),
            logged_at=request.logged_at,
            max_hold_days=10,
        )


@pytest.fixture
def base_response():
    return LogSwingCandidateResponse(
        ticker="BBRI",
        written=True,
        setup_match="MATCH",
        pattern="pattern",
        regime="RISK_ON",
        entry_price=Decimal("5000"),
        planned_stop=Decimal("4700"),
        planned_target=Decimal("5300"),
        failed_gates=(),
        candidate_accum_score=75.0,
    )


@pytest.fixture
def base_policy():
    return SimpleNamespace(max_hold_days=10)


def test_cli_uses_factory_and_logs_successfully(monkeypatch, base_response, base_policy):
    factory_calls = []

    def mock_factory(*, db_path, journal_path, with_regime, regime_universe, benchmark):
        factory_calls.append(
            {
                "db_path": db_path,
                "journal_path": journal_path,
                "with_regime": with_regime,
                "regime_universe": regime_universe,
                "benchmark": benchmark,
            }
        )
        workflow = FakeWorkflow(base_response, base_policy)
        return LogAccumulationTradeWorkflowBundle(workflow=workflow, warnings=())

    monkeypatch.setattr(trade_accum_cli, "create_log_accumulation_trade_workflow", mock_factory)

    result = runner.invoke(
        app,
        [
            "trade",
            "log",
            "--type",
            "swing",
            "--ticker",
            "bbri",
            "--window",
            "7",
            "--from-analysis",
            "--setup",
            "foreign-bounce",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Logged BBRI |" in result.stdout
    assert "score=75.0" in result.stdout
    assert "plan entry=5,000 stop=4,700 target=5,300 hold=10d" in result.stdout
    assert len(factory_calls) == 1
    assert factory_calls[0]["with_regime"] is False


def test_cli_calls_run_accumulation_log_command_from_router(
    monkeypatch, base_response, base_policy
):
    import src.adapters.cli.trade_log_router_commands as trade_log_router

    router_calls = []

    def mock_run_command(*args, **kwargs):
        router_calls.append((args, kwargs))

    monkeypatch.setattr(trade_log_router, "run_accumulation_log_command", mock_run_command)

    result = runner.invoke(
        app,
        ["trade", "log", "--type", "swing", "--ticker", "bbri"],
    )

    assert result.exit_code == 0
    assert len(router_calls) == 1
    assert router_calls[0][1]["ticker"] == "bbri"


def test_cli_renders_duplicate_message(monkeypatch, base_response, base_policy):
    dup_resp = LogSwingCandidateResponse(
        ticker="BBRI",
        written=False,
        setup_match=base_response.setup_match,
        pattern=base_response.pattern,
        regime=base_response.regime,
        entry_price=base_response.entry_price,
        planned_stop=base_response.planned_stop,
        planned_target=base_response.planned_target,
        failed_gates=base_response.failed_gates,
        candidate_accum_score=base_response.candidate_accum_score,
    )

    def mock_factory(**kwargs):
        workflow = FakeWorkflow(dup_resp, base_policy)
        return LogAccumulationTradeWorkflowBundle(workflow=workflow, warnings=())

    monkeypatch.setattr(trade_accum_cli, "create_log_accumulation_trade_workflow", mock_factory)

    result = runner.invoke(
        app,
        ["trade", "log", "--type", "swing", "--ticker", "bbri"],
    )

    assert result.exit_code == 0, result.stdout
    assert "Already logged BBRI" in result.stdout
    assert "no new row added" in result.stdout


def test_cli_renders_missing_candidate_warning(monkeypatch, base_response, base_policy):
    warn_resp = LogSwingCandidateResponse(
        ticker="BBRI",
        written=True,
        setup_match=base_response.setup_match,
        pattern=base_response.pattern,
        regime=base_response.regime,
        entry_price=base_response.entry_price,
        planned_stop=base_response.planned_stop,
        planned_target=base_response.planned_target,
        failed_gates=base_response.failed_gates,
        candidate_accum_score=None,
    )

    def mock_factory(**kwargs):
        workflow = FakeWorkflow(warn_resp, base_policy)
        return LogAccumulationTradeWorkflowBundle(workflow=workflow, warnings=())

    monkeypatch.setattr(trade_accum_cli, "create_log_accumulation_trade_workflow", mock_factory)

    result = runner.invoke(
        app,
        ["trade", "log", "--type", "swing", "--ticker", "bbri"],
    )

    assert result.exit_code == 0, result.stdout
    assert "Warning: no accumulation data for BBRI" in result.stderr


def test_cli_renders_failed_gates(monkeypatch, base_response, base_policy):
    gates_resp = LogSwingCandidateResponse(
        ticker="BBRI",
        written=True,
        setup_match="NO_MATCH",
        pattern=base_response.pattern,
        regime=base_response.regime,
        entry_price=base_response.entry_price,
        planned_stop=base_response.planned_stop,
        planned_target=base_response.planned_target,
        failed_gates=("gate_rsi", "gate_trend"),
        candidate_accum_score=base_response.candidate_accum_score,
    )

    def mock_factory(**kwargs):
        workflow = FakeWorkflow(gates_resp, base_policy)
        return LogAccumulationTradeWorkflowBundle(workflow=workflow, warnings=())

    monkeypatch.setattr(trade_accum_cli, "create_log_accumulation_trade_workflow", mock_factory)

    result = runner.invoke(
        app,
        ["trade", "log", "--type", "swing", "--ticker", "bbri", "--from-analysis"],
    )

    assert result.exit_code == 0, result.stdout
    assert "Failed gates:" in result.stdout
    assert "  - gate_rsi" in result.stdout
    assert "  - gate_trend" in result.stdout


def test_cli_prints_regime_factory_warnings_to_stderr_and_logs(
    monkeypatch, base_response, base_policy
):
    def mock_factory(**kwargs):
        workflow = FakeWorkflow(base_response, base_policy)
        return LogAccumulationTradeWorkflowBundle(
            workflow=workflow, warnings=("Warning: could not resolve regime universe: Some error",)
        )

    monkeypatch.setattr(trade_accum_cli, "create_log_accumulation_trade_workflow", mock_factory)

    result = runner.invoke(
        app,
        ["trade", "log", "--type", "swing", "--ticker", "bbri"],
    )

    assert result.exit_code == 0
    assert "Warning: could not resolve regime universe: Some error" in result.stderr
    assert "Logged BBRI |" in result.stdout
