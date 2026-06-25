"""
Tests for accumulation audit CLI wiring.
"""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_accumulation_audit_unknown_setup_error():
    result = runner.invoke(
        app,
        ["analyze", "accum-audit", "--setup", "unknown-setup"],
    )

    assert result.exit_code != 0
    output = result.output or result.stdout
    assert "unknown setup" in output.lower()
    assert "foreign-bounce" in output
