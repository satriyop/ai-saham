"""Tests for screen CLI commands."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.candle import Candle
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

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


def test_confirm_log_appends_confirmation_sidecar(tmp_path):
    confirmation = tmp_path / "last-confirmation.json"
    journal = tmp_path / "confirmations.csv"
    confirmation.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [
                    {
                        "ticker": "BBCA",
                        "decision": "ENTER",
                        "opening_price": "9050",
                        "planned_entry": "9050",
                        "stop_loss_price": "8900",
                        "stop_pct": "1.7",
                        "reasons": ["open inside entry range"],
                        "iev": 450000,
                        "trend": "BULLISH",
                        "rsi": "52",
                        "gap_pct": "0.6",
                        "accum_tag": "BACKED",
                        "fvwap_discount_pct": "2.4",
                    }
                ],
            }
        )
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "confirm-log",
            "--confirmation",
            str(confirmation),
            "--journal",
            str(journal),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Logged 1 confirmation" in result.stdout
    assert "BBCA" in journal.read_text()


def test_confirm_review_outputs_bucket_tables(tmp_path):
    journal = tmp_path / "confirmations.csv"
    db_path = tmp_path / "data.db"

    confirmation = tmp_path / "last-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [
                    {
                        "ticker": "BBCA",
                        "decision": "ENTER",
                        "opening_price": "9050",
                        "planned_entry": "9050",
                        "stop_loss_price": "8900",
                        "stop_pct": "1.7",
                        "reasons": ["open inside entry range"],
                        "iev": 450000,
                        "trend": "BULLISH",
                        "rsi": "52",
                        "gap_pct": "0.6",
                        "accum_tag": "BACKED",
                        "fvwap_discount_pct": "2.4",
                    }
                ],
            }
        )
    )
    runner.invoke(
        app,
        [
            "screen",
            "confirm-log",
            "--confirmation",
            str(confirmation),
            "--journal",
            str(journal),
        ],
    )

    repo = SQLiteMarketRepository(db_path=db_path)
    repo.save_candles(
        [
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 12),
                open=Decimal("9050"),
                high=Decimal("9225"),
                low=Decimal("9000"),
                close=Decimal("9200"),
                volume=1000000,
            )
        ]
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "confirm-review",
            "--journal",
            str(journal),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION REVIEW" in result.stdout
    assert "decision:ENTER" in result.stdout
    assert "gap:0-1" in result.stdout


def test_confirm_outcome_updates_logged_confirmation(tmp_path):
    journal = tmp_path / "confirmations.csv"
    confirmation = tmp_path / "last-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [
                    {
                        "ticker": "BBCA",
                        "decision": "ENTER",
                        "opening_price": "9050",
                        "planned_entry": "9050",
                        "stop_loss_price": "8900",
                        "stop_pct": "1.7",
                        "reasons": ["open inside entry range"],
                    }
                ],
            }
        )
    )
    runner.invoke(
        app,
        [
            "screen",
            "confirm-log",
            "--confirmation",
            str(confirmation),
            "--journal",
            str(journal),
        ],
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "confirm-outcome",
            "BBCA",
            "--date",
            "2026-06-12",
            "--entry",
            "9050",
            "--exit",
            "9200",
            "--result",
            "target",
            "--notes",
            "manual exit",
            "--journal",
            str(journal),
            "--db",
            str(tmp_path / "data.db"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Recorded outcome for BBCA" in result.stdout
    assert "R=+1.00R" in result.stdout
    csv_text = journal.read_text()
    assert "manual exit" in csv_text
    assert "target" in csv_text
