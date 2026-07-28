"""ADR-054 S2: plan swing is structure desk messaging, not second analysis."""

from __future__ import annotations

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_plan_group_help_is_structure_desk() -> None:
    result = runner.invoke(app, ["plan", "--help"])
    assert result.exit_code == 0
    # Rich may wrap "screen accum" across lines — normalize whitespace.
    compact = " ".join(result.stdout.lower().split())
    assert "structure" in compact or "adr-054" in compact
    assert "screen" in compact and "accum" in compact


def test_plan_swing_help_is_structure_first() -> None:
    result = runner.invoke(app, ["plan", "swing", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    compact = " ".join(out.lower().split())
    assert "structure" in compact
    assert "screen" in compact and "accum" in compact
    assert "--capital" in out
    # Not sold as the multi-command morning deep-dive replacement
    assert "replaces the multi-command morning workflow" not in compact
