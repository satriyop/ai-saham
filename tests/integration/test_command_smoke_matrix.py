"""Phase 2E command smoke matrix for key user-facing workflows."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
import src.adapters.cli.screen_pre_open_commands as screen_pre_open_commands
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from tests.integration.conftest import generate_test_candles

runner = CliRunner()


def _tx(code: str, buy: str = "70000000", sell: str = "20000000") -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=BrokerType.FOREIGN,
        buy_lot=700,
        sell_lot=200,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _broker_summary(ticker: str, day: date) -> BrokerSummary:
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(_tx("AK"),),
        top_sellers=(_tx("BK", buy="10000000", sell="30000000"),),
        foreign_buy_value=Decimal("120000000"),
        foreign_sell_value=Decimal("50000000"),
        foreign_buy_lot=1200,
        foreign_sell_lot=500,
        total_value=Decimal("500000000"),
        total_lot=5000,
        source="idx",
    )


def _seed_db(tmp_path: Path, ticker: str = "BBCA") -> Path:
    db_path = tmp_path / "data.db"
    start = date(2026, 1, 1)
    candles = generate_test_candles(
        days=180,
        start_price=Decimal("1000"),
        ticker=ticker,
        start_date=start,
    )
    market_repo = SQLiteMarketRepository(db_path=db_path)
    market_repo.save_candles(candles)
    broker_repo = SQLiteBrokerRepository(db_path)
    broker_repo.save_broker_summaries([
        _broker_summary(ticker, candle.date)
        for candle in candles[-40:]
    ])
    return db_path


def _json_stdout(result) -> dict:
    assert result.stdout.lstrip().startswith("{"), result.stdout
    return json.loads(result.stdout)


def test_analyze_swing_table_and_json_contracts(temp_workspace, monkeypatch):
    monkeypatch.chdir(temp_workspace)
    db_path = _seed_db(temp_workspace)

    table = runner.invoke(
        app,
        ["analyze", "swing", "BBCA", "--no-refresh", "--db", str(db_path)],
    )
    assert table.exit_code == 0, table.output
    assert "Swing Analysis - BBCA" in table.stdout
    assert "Verdict" in table.stdout
    assert "Candidate Actions" not in table.stdout

    js = runner.invoke(
        app,
        [
            "analyze", "swing", "BBCA",
            "--no-refresh",
            "--format", "json",
            "--db", str(db_path),
        ],
    )
    assert js.exit_code == 0, js.output
    payload = _json_stdout(js)
    assert payload["artifact_type"] == "swing_analysis"
    assert payload["schema_version"] == 1
    assert payload["accumulation"]["accum_score"] == payload["accumulation"]["score"]
    assert "trade_setup" in payload


def test_screen_accum_table_multi_and_json_contracts(temp_workspace, monkeypatch):
    monkeypatch.chdir(temp_workspace)
    db_path = _seed_db(temp_workspace)

    table = runner.invoke(app, ["screen", "accum", "BBCA", "--db", str(db_path)])
    assert table.exit_code == 0, table.output
    assert "Candidate Actions" in table.stdout
    assert "Verdict" not in table.stdout

    js = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--format", "json", "--db", str(db_path)],
    )
    assert js.exit_code == 0, js.output
    payload = _json_stdout(js)
    assert payload["artifact_type"] == "accumulation_screen"
    assert payload["schema_version"] == 1
    assert payload["candidates"][0]["accum_score"] is not None

    multi = runner.invoke(app, ["screen", "accum", "BBCA", "--multi", "--db", str(db_path)])
    assert multi.exit_code == 0, multi.output
    assert "multi-window" in multi.stdout


def test_pre_open_and_confirm_sidecar_contracts(temp_workspace, monkeypatch):
    db_path = _seed_db(temp_workspace)
    session_path = temp_workspace / "pre-open.json"
    confirm_path = temp_workspace / "confirm.json"
    default_sidecar = temp_workspace / "default-pre-open.json"
    monkeypatch.setattr(screen_pre_open_commands, "DEFAULT_SIDECAR_PATH", default_sidecar)

    pre_open = runner.invoke(
        app,
        [
            "screen", "pre-open",
            "--movers-json", '[{"ticker":"BBCA","iev":150000}]',
            "--order-books-json", '{"BBCA":{"price":1000,"volume":50000}}',
            "--allow-non-trading-day",
            "--db", str(db_path),
        ],
    )
    assert pre_open.exit_code == 0, pre_open.output
    assert "PRE-OPEN CANDIDATE PLAN" in pre_open.stdout
    assert "VERDICT:" not in pre_open.stdout

    # Write an explicit sidecar path for the confirm step; screen pre-open uses
    # the configured default path, so this compact fixture keeps the smoke stable.
    session_path.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "pre_open_session",
        "screened_at": "2026-06-12",
        "market_regime": None,
        "candidates": [{
            "ticker": "BBCA",
            "iev": 150000,
            "gap_pct": "1.0",
            "entry_range_low": "900",
            "entry_range_high": "1100",
            "suggested_entry": "1000",
            "atr_stop": "950",
            "trend": "BULLISH",
            "rsi": "55",
            "accum_tag": "BACKED",
            "broker_accum_score": 70.0,
            "accum_streak": 3,
            "foreign_vwap": "980",
            "fvwap_discount_pct": 2.0,
            "prev_high": 1100,
            "prev_low": 900,
        }],
    }))

    confirm = runner.invoke(
        app,
        [
            "trade", "confirm",
            "--session", str(session_path),
            "--output", str(confirm_path),
            "--opening-json", '{"BBCA":1000}',
        ],
    )
    assert confirm.exit_code == 0, confirm.output
    assert "INTRADAY CONFIRMATION" in confirm.stdout
    saved = json.loads(confirm_path.read_text())
    assert saved["artifact_type"] == "intraday_confirmation"
    assert saved["confirmations"][0]["decision"] == "ENTER"


def test_backtest_and_audit_json_contracts(temp_workspace, monkeypatch):
    db_path = _seed_db(temp_workspace)

    swing_bt = runner.invoke(
        app,
        [
            "trade", "backtest-swing", "BBCA",
            "--start", "2026-06-01",
            "--end", "2026-06-20",
            "--format", "json",
            "--db", str(db_path),
        ],
    )
    assert swing_bt.exit_code == 0, swing_bt.output
    payload = _json_stdout(swing_bt)
    assert payload["artifact_type"] == "swing_backtest"

    intraday_bt = runner.invoke(
        app,
        [
            "trade", "backtest-intraday", "BBCA",
            "--start", "2026-06-01",
            "--end", "2026-06-20",
            "--format", "json",
            "--db", str(db_path),
        ],
    )
    assert intraday_bt.exit_code == 0, intraday_bt.output
    payload = _json_stdout(intraday_bt)
    assert payload["artifact_type"] == "intraday_proxy_simulation"

    audit = runner.invoke(
        app,
        [
            "analyze", "accum-audit", "BBCA",
            "--start", "2026-06-01",
            "--end", "2026-06-20",
            "--format", "json",
            "--db", str(db_path),
        ],
    )
    assert audit.exit_code == 0, audit.output
    payload = _json_stdout(audit)
    assert payload["artifact_type"] == "accumulation_audit"
