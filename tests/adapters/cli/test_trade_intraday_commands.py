"""Tests for intraday trade CLI commands."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.candle import Candle
from src.domain.entities.trade_tick import TradeTick
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


def _write_confirmation(path: Path, include_context: bool = False) -> None:
    row = {
        "ticker": "BBCA",
        "decision": "ENTER",
        "opening_price": "9050",
        "planned_entry": "9050",
        "stop_loss_price": "8900",
        "stop_pct": "1.7",
        "reasons": ["open inside entry range"],
    }
    if include_context:
        row.update(
            {
                "iev": 450000,
                "trend": "BULLISH",
                "rsi": "52",
                "gap_pct": "0.6",
                "accum_tag": "BACKED",
                "fvwap_discount_pct": "2.4",
            }
        )
    path.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [row],
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
            "trade", "confirm",
            "--session", str(session),
            "--output", str(output),
            "--opening-json", '{"BBCA":9050,"GOTO":245}',
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION" in result.stdout
    assert "BBCA" in result.stdout
    assert "ENTER" in result.stdout
    assert "GOTO" in result.stdout
    assert "SKIP" in result.stdout

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
            "trade", "confirm",
            "--session", str(session),
            "--opening-json", '[{"BBCA":9050}]',
        ],
    )

    assert result.exit_code == 1
    assert "--opening-json must be a JSON object" in result.output


def test_intraday_confirm_open_auto_uses_stockbit_provider_stubs(tmp_path, monkeypatch):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    _write_sidecar(session)

    class FakeBrokerProvider:
        def __init__(self, *args, **kwargs):
            pass

        def is_authenticated(self):
            return True

    class FakeRunningTradeProvider:
        def __init__(self, broker_provider):
            pass

        def fetch_running_trade(self, ticker: str, limit: int = 80):
            if ticker != "BBCA":
                return []
            return [
                TradeTick(
                    ticker="BBCA",
                    timestamp=datetime(2026, 6, 12, 9, 1, tzinfo=ZoneInfo("Asia/Jakarta")),
                    price=9050,
                    lot=10,
                    buyer_broker_code="AK",
                    seller_broker_code="YP",
                    trade_type="RG",
                )
            ]

    class FakeOrderBookProvider:
        def __init__(self, broker_provider):
            pass

        def fetch_snapshot(self, ticker: str):
            return None

    import src.infrastructure.browser.playwright_stockbit as playwright_stockbit
    import src.infrastructure.browser.stockbit_order_book as stockbit_order_book
    import src.infrastructure.browser.stockbit_running_trade as stockbit_running_trade

    monkeypatch.setattr(playwright_stockbit, "StockbitPlaywrightBrokerProvider", FakeBrokerProvider)
    monkeypatch.setattr(
        stockbit_running_trade,
        "StockbitRunningTradeProvider",
        FakeRunningTradeProvider,
    )
    monkeypatch.setattr(stockbit_order_book, "StockbitOrderBookProvider", FakeOrderBookProvider)

    result = runner.invoke(
        app,
        [
            "trade", "confirm",
            "--session", str(session),
            "--output", str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    saved = json.loads(output.read_text())
    first = saved["confirmations"][0]
    assert first["ticker"] == "BBCA"
    assert first["opening_price"] == "9050"
    assert first["opening_price_source"] == "running_trade_first_tick"
    assert first["opening_price_confidence"] == "HIGH"
    assert first["auto_confirmed"] is True
    assert first["manual_override"] is False


def test_trade_log_intraday_writes_confirmation_sidecar(tmp_path):
    confirmation = tmp_path / "last-confirmation.json"
    journal = tmp_path / "confirmations.csv"
    _write_confirmation(confirmation)

    result = runner.invoke(
        app,
        [
            "trade", "log", "intraday",
            "--confirmation", str(confirmation),
            "--journal", str(journal),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Logged 1 confirmation" in result.stdout
    assert "BBCA" in journal.read_text()


def test_confirm_review_outputs_bucket_tables(tmp_path):
    journal = tmp_path / "confirmations.csv"
    db_path = tmp_path / "data.db"
    confirmation = tmp_path / "last-confirmation.json"
    _write_confirmation(confirmation, include_context=True)

    runner.invoke(
        app,
        [
            "trade", "log", "intraday",
            "--confirmation", str(confirmation),
            "--journal", str(journal),
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
            "trade", "review", "intraday",
            "--journal", str(journal),
            "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION REVIEW" in result.stdout
    assert "decision:ENTER" in result.stdout
    assert "gap:0-1" in result.stdout


def test_trade_outcome_updates_logged_confirmation(tmp_path):
    journal = tmp_path / "confirmations.csv"
    confirmation = tmp_path / "last-confirmation.json"
    _write_confirmation(confirmation)
    runner.invoke(
        app,
        [
            "trade", "log", "intraday",
            "--confirmation", str(confirmation),
            "--journal", str(journal),
        ],
    )

    result = runner.invoke(
        app,
        [
            "trade", "outcome", "BBCA",
            "--date", "2026-06-12",
            "--entry", "9050",
            "--exit", "9200",
            "--result", "target",
            "--notes", "manual exit",
            "--journal", str(journal),
            "--db", str(tmp_path / "data.db"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Recorded outcome for BBCA" in result.stdout
    assert "R=+1.00R" in result.stdout
    csv_text = journal.read_text()
    assert "manual exit" in csv_text
    assert "target" in csv_text
