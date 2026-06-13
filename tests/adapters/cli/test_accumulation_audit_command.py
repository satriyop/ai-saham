"""
Tests for accumulation audit CLI wiring.
"""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_accumulation_audit_unknown_preset_error():
    result = runner.invoke(
        app,
        ["swing", "audit", "--preset", "unknown-preset"],
    )

    assert result.exit_code != 0
    output = result.output or result.stdout
    assert "unknown preset" in output.lower()
    assert "foreign-bounce" in output
