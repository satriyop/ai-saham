"""Tests for screen CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def _write_sidecar(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "screened_at": "2026-06-12",
                "candidates": [
                    {
                        "ticker": "BBCA",
                        "iev": 450000,
                        "gap_pct": "0.6",
                        "entry_range_low": "8800",
                        "entry_range_high": "9300",
                        "suggested_entry": "9050",
                        "atr_stop": "8900",
                        "trend": "BULLISH",
                        "rsi": "52",
                        "accum_tag": "BACKED",
                    },
                    {
                        "ticker": "GOTO",
                        "iev": 155000,
                        "gap_pct": "4.2",
                        "entry_range_low": "228",
                        "entry_range_high": "242",
                        "suggested_entry": "235",
                        "atr_stop": "221",
                        "trend": "BEARISH",
                        "rsi": "73",
                    },
                ],
            }
        )
    )


def test_confirm_open_outputs_decisions_and_writes_sidecar(tmp_path):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "screen",
            "confirm-open",
            "--session",
            str(session),
            "--output",
            str(output),
            "--opening-json",
            '{"BBCA":9050,"GOTO":245}',
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY OPEN CONFIRMATION" in result.stdout
    assert "BBCA" in result.stdout
    assert "ENTER" in result.stdout
    assert "GOTO" in result.stdout
    assert "SKIP_GAP_UP" in result.stdout

    saved = json.loads(output.read_text())
    assert saved["confirmed_at"] == "2026-06-12"
    assert saved["confirmations"][0]["decision"] == "ENTER"
    assert saved["confirmations"][1]["decision"] == "SKIP_GAP_UP"


def test_confirm_open_rejects_non_object_opening_json(tmp_path):
    session = tmp_path / "last-session.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "screen",
            "confirm-open",
            "--session",
            str(session),
            "--opening-json",
            '[{"BBCA":9050}]',
        ],
    )

    assert result.exit_code == 1
    assert "--opening-json must be a JSON object" in result.output
