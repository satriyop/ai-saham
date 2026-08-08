"""CLI tests for desk-centric view broker commands."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.broker_flow import BrokerDailyFlow
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

runner = CliRunner()


def _seed(repo: SQLiteBrokerRepository) -> None:
    d = date(2026, 7, 23)
    repo.save_broker_daily_flows(
        [
            BrokerDailyFlow(
                ticker="AMMN",
                broker_code="AK",
                broker_name="UBS",
                date=d,
                buy_lot=100,
                sell_lot=0,
                net_lot=100,
                buy_value=Decimal("1000"),
                sell_value=Decimal("0"),
                net_value=Decimal("1000"),
                avg_buy_price=Decimal("0"),
                avg_sell_price=Decimal("0"),
                avg_price=Decimal("0"),
                buy_pct=0.0,
                sell_pct=0.0,
            ),
            BrokerDailyFlow(
                ticker="BBCA",
                broker_code="AK",
                broker_name="UBS",
                date=d,
                buy_lot=0,
                sell_lot=50,
                net_lot=-50,
                buy_value=Decimal("0"),
                sell_value=Decimal("500"),
                net_value=Decimal("-500"),
                avg_buy_price=Decimal("0"),
                avg_sell_price=Decimal("0"),
                avg_price=Decimal("0"),
                buy_pct=0.0,
                sell_pct=0.0,
            ),
        ]
    )


def test_view_broker_top_stocks_ak(tmp_path: Path):
    db = tmp_path / "b.db"
    repo = SQLiteBrokerRepository(db)
    _seed(repo)
    result = runner.invoke(app, ["view", "broker", "top-stocks", "AK", "--db", str(db)])
    assert result.exit_code == 0
    assert "AMMN" in result.stdout
    assert "BBCA" in result.stdout
    assert "Tracked desk" in result.stdout


def test_view_broker_show_ak(tmp_path: Path):
    db = tmp_path / "b.db"
    _seed(SQLiteBrokerRepository(db))
    result = runner.invoke(app, ["view", "broker", "show", "AK", "--db", str(db)])
    assert result.exit_code == 0
    assert "Broker Desk" in result.stdout
    assert "AK" in result.stdout


def test_view_broker_list():
    result = runner.invoke(app, ["view", "broker", "list"])
    assert result.exit_code == 0
    assert "Tracked broker desks" in result.stdout


def test_view_broker_show_json(tmp_path: Path):
    db = tmp_path / "b.db"
    _seed(SQLiteBrokerRepository(db))
    result = runner.invoke(
        app, ["view", "broker", "show", "AK", "--db", str(db), "--format", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["subject"] == {"kind": "desk", "id": "AK"}
    assert payload["verb"] == "show"
    assert payload["status"] == "ok"
    assert payload["data"]["broker_code"] == "AK"
    assert payload["data"]["top_buy_stocks"][0]["ticker"] == "AMMN"


def test_view_broker_top_stocks_json(tmp_path: Path):
    db = tmp_path / "b.db"
    _seed(SQLiteBrokerRepository(db))
    result = runner.invoke(
        app,
        ["view", "broker", "top-stocks", "AK", "--db", str(db), "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verb"] == "top-stocks"
    tickers = {r["ticker"] for r in payload["data"]["top_buy_stocks"]} | {
        r["ticker"] for r in payload["data"]["top_sell_stocks"]
    }
    assert "AMMN" in tickers
    assert "BBCA" in tickers


def test_view_broker_flow_json(tmp_path: Path):
    db = tmp_path / "b.db"
    _seed(SQLiteBrokerRepository(db))
    result = runner.invoke(
        app, ["view", "broker", "flow", "AK", "--db", str(db), "--format", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verb"] == "flow"
    assert payload["data"]["days"][0]["date"] == "2026-07-23"
    assert payload["data"]["days"][0]["ticker_count"] == 2


def test_view_broker_history_json(tmp_path: Path):
    db = tmp_path / "b.db"
    _seed(SQLiteBrokerRepository(db))
    result = runner.invoke(
        app,
        [
            "view",
            "broker",
            "history",
            "AK",
            "--db",
            str(db),
            "--format",
            "json",
            "--ticker",
            "BBCA",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verb"] == "history"
    assert payload["data"]["pinned_ticker"] == "BBCA"
    assert len(payload["data"]["flows"]) == 1
    assert payload["data"]["flows"][0]["ticker"] == "BBCA"


def test_view_broker_list_json():
    result = runner.invoke(app, ["view", "broker", "list", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verb"] == "list"
    assert isinstance(payload["data"]["desks"], list)
    assert any(d["code"] == "AK" for d in payload["data"]["desks"])


def test_view_broker_status_json():
    result = runner.invoke(app, ["view", "broker", "status", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verb"] == "status"
    providers = {p["provider"] for p in payload["data"]["providers"]}
    assert "idx" in providers
    assert "stockbit" in providers


def test_view_broker_invalid_format_exits_2(tmp_path: Path):
    db = tmp_path / "b.db"
    _seed(SQLiteBrokerRepository(db))
    result = runner.invoke(
        app, ["view", "broker", "show", "AK", "--db", str(db), "--format", "yaml"]
    )
    assert result.exit_code == 1  # user_input for invalid --format
