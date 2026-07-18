from __future__ import annotations

from datetime import date
import pytest
from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.analyze_signal_audit_commands import _display_report
from src.domain.value_objects.signal_audit import SignalAuditEntry, SignalAuditReport


def test_display_report_wording(capsys):
    report = SignalAuditReport(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 3),
        entries=(
            SignalAuditEntry(
                factor="bandar_intensity",
                present=True,
                raw_value="broad_score=6/6",
                component_score=100.0,
                configured_weight=0.20,
                active_weight=0.20,
                weighted_contribution=20.0,
            ),
        ),
        final_score=75,
        strength="STRONG",
        entry_quality="ENTER",
        coverage_warning=None,
        factors_present=1,
        factors_missing=5,
        renormalized_score=100,
    )

    _display_report(report)
    captured = capsys.readouterr()

    # Assert visible wording is correctly changed
    assert "Archived Signal Baseline Audit" in captured.out
    assert "ARCHIVED BASELINE SCORE" in captured.out
    assert "Archived factor presence" in captured.out

    # Assert old strings are NOT present
    assert "Signal Audit" not in captured.out.replace("Archived Signal Baseline Audit", "")
    assert "COMPOSITE SCORE" not in captured.out
    assert "Coverage" not in captured.out.replace("Archived factor presence", "")
    # Check that neither archived score is described as canonical
    assert "canonical score" not in captured.out.lower()
    assert "canonical baseline score" not in captured.out.lower()

    # Assert numeric values and factor rows remain unchanged
    assert "bandar_intensity" in captured.out
    assert "broad_score=6/6" in captured.out
    assert "100.0" in captured.out
    assert "75/100" in captured.out
    assert "STRONG" in captured.out
    assert "ENTER" in captured.out
    assert "100/100" in captured.out


def test_signal_audit_command_help():
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "signal-audit", "--help"])
    assert result.exit_code == 0

    # Assert help contains:
    assert "archived six-factor signal baseline" in result.stdout
    assert "does not calculate or display the canonical" in result.stdout

    # Assert help does not contain:
    assert "Audit current SignalEngine inputs" not in result.stdout
    assert "alongside the canonical score" not in result.stdout
