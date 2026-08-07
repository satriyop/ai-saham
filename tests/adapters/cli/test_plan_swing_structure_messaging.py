"""ADR-054 S2: plan swing is structure desk messaging, not second analysis."""

from __future__ import annotations

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.plan_swing_commands import _echo_structure_desk_footer

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
    # Analysis suite belongs on screen, not plan
    assert "--with-market-context" not in out
    assert "--with-technical-gate" not in out
    assert "--with-flow-detail" not in out
    assert "--full" not in out or "screen accum" in compact
    # Not sold as the multi-command morning deep-dive replacement
    assert "replaces the multi-command morning workflow" not in compact


def test_footer_offers_from_plan_only_when_handoff_ready(capsys) -> None:
    _echo_structure_desk_footer(
        ticker="BBCA",
        capital=10_000_000,
        setup_name="foreign-bounce",
        output_format="table",
        judgment_available=True,
        handoff_ready=False,
    )
    assert "--from-plan" not in capsys.readouterr().out

    _echo_structure_desk_footer(
        ticker="BBCA",
        capital=10_000_000,
        setup_name="foreign-bounce",
        output_format="table",
        judgment_available=True,
        handoff_ready=True,
    )
    assert "--from-plan" in capsys.readouterr().out


def test_footer_explains_unavailable_screen_judgment(capsys) -> None:
    _echo_structure_desk_footer(
        ticker="BBCA",
        capital=10_000_000,
        setup_name=None,
        output_format="table",
        judgment_available=False,
        handoff_ready=False,
    )
    output = capsys.readouterr().out
    assert "Screen judgment unavailable" in output
    assert "saham screen accum BBCA" in output
    assert "--from-plan" not in output
