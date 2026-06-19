"""Tests for IEV fetch CLI command registration."""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_fetch_iev_help_is_registered():
    result = runner.invoke(app, ["fetch", "iev", "--help"])

    assert result.exit_code == 0
    assert "Capture today's IEV mover ranking" in result.stdout
    assert "--top-n" in result.stdout
