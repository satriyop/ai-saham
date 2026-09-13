"""Accum retirement leaves corpus production, pre-open, and backtests available."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.value_objects.learning_artifacts import AssessmentPurpose

runner = CliRunner()


@pytest.mark.parametrize("command", ["evaluate", "replay"])
@pytest.mark.parametrize("help_only", [False, True])
def test_retired_accum_commands_fail_before_opening_database(
    command: str, help_only: bool, tmp_path: Path
) -> None:
    db_path = tmp_path / "must-not-exist.db"
    options = ["--help"] if help_only else ["--db", str(db_path)]

    result = runner.invoke(app, ["research", "accum", command, *options])

    assert result.exit_code == 2, result.output
    assert f"No such command '{command}'" in result.output
    assert not db_path.exists()


def test_accum_help_lists_producer_commands_without_retired_commands() -> None:
    result = runner.invoke(app, ["research", "accum", "--help"])

    assert result.exit_code == 0, result.output
    for command in (
        "capture",
        "catch-up",
        "backfill",
        "backfill-phase-ledger",
        "sync-session-calendar",
        "labels",
        "status",
    ):
        assert command in result.output
    assert "evaluate" not in result.output
    assert "replay" not in result.output
    assert "ml-saham" in result.output


def test_pre_open_evaluate_still_delegates_to_shared_cohort_evaluator(
    monkeypatch, tmp_path: Path
) -> None:
    calls = []

    def record_evaluation(purpose, **kwargs):
        calls.append((purpose, kwargs))

    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_evaluate_commands.evaluate_cohort",
        record_evaluation,
    )
    db_path = tmp_path / "pre-open.db"
    result = runner.invoke(
        app,
        [
            "research",
            "pre-open",
            "evaluate",
            "--compatibility-id",
            "pre-open-cohort",
            "--db",
            str(db_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        (
            AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            {"compatibility_id": "pre-open-cohort", "db_path": db_path, "fmt": "json"},
        )
    ]


def test_historical_accum_audit_keeps_documented_options() -> None:
    result = runner.invoke(app, ["backtest", "screen", "accum", "--help"])

    assert result.exit_code == 0, result.output
    for option in (
        "--universe",
        "--setup",
        "--start",
        "--window",
        "--min-foreign-flow-score",
        "--simulate-exits",
    ):
        assert option in result.output
    assert "--min-score" not in result.output
