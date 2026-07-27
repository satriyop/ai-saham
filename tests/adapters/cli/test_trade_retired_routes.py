"""Retired trade CLI routes must fail closed (clean break, no aliases)."""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_retired_trade_routes_fail() -> None:
    routes = (
        ["trade", "log"],
        ["trade", "outcome"],
        ["trade", "review"],
        ["trade", "size"],
        ["trade", "swing"],
        ["trade", "backtest-intraday"],
        ["trade", "migrate-journal"],
        ["trade", "confirm"],
        ["trade", "intraday"],
    )
    for args in routes:
        result = runner.invoke(app, [*args, "--help"])
        assert result.exit_code != 0, args


def test_research_accumulation_name_removed() -> None:
    result = runner.invoke(app, ["research", "accumulation", "--help"])
    assert result.exit_code != 0
