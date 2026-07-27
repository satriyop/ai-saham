"""Retired: saham analyze compare and swing-compare (ADR-050)."""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_analyze_compare_retired() -> None:
    assert runner.invoke(app, ["analyze", "compare", "--help"]).exit_code != 0


def test_analyze_swing_compare_retired() -> None:
    assert runner.invoke(app, ["analyze", "swing-compare", "--help"]).exit_code != 0


def test_analyze_swing_retired_in_favor_of_plan() -> None:
    assert runner.invoke(app, ["analyze", "swing", "--help"]).exit_code != 0
    assert runner.invoke(app, ["plan", "swing", "--help"]).exit_code == 0
