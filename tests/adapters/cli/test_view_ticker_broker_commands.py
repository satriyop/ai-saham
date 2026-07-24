"""Tests for stock-axis ticker broker deep-dive commands."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
    ForeignFlowPoint,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

runner = CliRunner()


def test_view_ticker_foreign_history_reads_cached_points_only(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    repo = SQLiteBrokerRepository(db_path)
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2024, 1, 15),
            net_val=Decimal("1000000"),
            net_lot=100,
            avg_price=Decimal("10000"),
            source="stockbit",
        ),
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2024, 1, 16),
            net_val=Decimal("-500000"),
            net_lot=-50,
            avg_price=Decimal("9900"),
            source="stockbit",
        ),
    ])

    result = runner.invoke(
        app,
        [
            "view", "ticker", "foreign-history", "BBCA",
            "--days", "2", "--source", "stockbit", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Foreign Flow History for BBCA" in result.stdout
    assert "2024-01-15" in result.stdout
    assert "2024-01-16" in result.stdout


def test_view_ticker_foreign_history_json_output(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    repo = SQLiteBrokerRepository(db_path)
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2024, 1, 15),
            net_val=Decimal("1000000"),
            net_lot=100,
            avg_price=Decimal("10000"),
            source="stockbit",
        ),
    ])

    result = runner.invoke(
        app,
        [
            "view", "ticker", "foreign-history", "BBCA",
            "--source", "stockbit", "--format", "json", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["subject"] == {"kind": "ticker", "id": "BBCA"}
    assert payload["verb"] == "foreign-history"
    assert payload["status"] == "ok"
    assert payload["source"] == "stockbit"
    assert payload["data"]["points"] == [
        {
            "ticker": "BBCA",
            "date": "2024-01-15",
            "source": "stockbit",
            "net_val": "1000000",
            "net_lot": 100,
            "avg_price": "10000",
        }
    ]


def test_view_ticker_deep_dives_reject_invalid_format(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "view", "ticker", "foreign-history", "BBCA",
            "--format", "xml", "--db", str(tmp_path / "x.db"),
        ],
    )
    assert result.exit_code == 2
    assert "Invalid --format" in result.stdout or "Invalid --format" in result.stderr


def test_view_ticker_top_brokers_falls_back_to_tracked_daily_flow(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    repo = SQLiteBrokerRepository(db_path)
    d = date(2026, 7, 23)
    repo.save_broker_summaries([
        BrokerSummary(
            ticker="BBCA",
            date=d,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("482513615000"),
            foreign_sell_value=Decimal("960770270000"),
            foreign_buy_lot=1000,
            foreign_sell_lot=2000,
            total_value=Decimal("5000000000000"),
            total_lot=50000,
            source="idx",
        ),
    ])
    repo.save_broker_daily_flows([
        BrokerDailyFlow(
            ticker="BBCA",
            broker_code="YP",
            broker_name="YP",
            date=d,
            buy_lot=100,
            sell_lot=10,
            net_lot=90,
            buy_value=Decimal("88505637500"),
            sell_value=Decimal("16410095000"),
            net_value=Decimal("72095542500"),
            avg_buy_price=Decimal("0"),
            avg_sell_price=Decimal("0"),
            avg_price=Decimal("0"),
            buy_pct=0.0,
            sell_pct=0.0,
        ),
        BrokerDailyFlow(
            ticker="BBCA",
            broker_code="RX",
            broker_name="RX",
            date=d,
            buy_lot=10,
            sell_lot=200,
            net_lot=-190,
            buy_value=Decimal("31211220000"),
            sell_value=Decimal("194428857500"),
            net_value=Decimal("-163217637500"),
            avg_buy_price=Decimal("0"),
            avg_sell_price=Decimal("0"),
            avg_price=Decimal("0"),
            buy_pct=0.0,
            sell_pct=0.0,
        ),
    ])

    result = runner.invoke(
        app,
        ["view", "ticker", "top-brokers", "BBCA", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Tracked brokers (not full market top)" in result.stdout
    assert "Top Buyers (tracked brokers)" in result.stdout
    assert "YP" in result.stdout
    assert "RX" in result.stdout
    assert "Local" in result.stdout
    assert "Foreign" in result.stdout


def test_view_ticker_top_brokers_uses_summary_tops_when_present(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    repo = SQLiteBrokerRepository(db_path)
    d = date(2026, 6, 12)
    repo.save_broker_summaries([
        BrokerSummary(
            ticker="BBCA",
            date=d,
            top_buyers=(
                BrokerTransaction(
                    broker_code="ZP",
                    broker_name="ZP",
                    broker_type=BrokerType.FOREIGN,
                    buy_lot=100,
                    sell_lot=0,
                    buy_value=Decimal("1000"),
                    sell_value=Decimal("0"),
                    avg_buy_price=Decimal("10"),
                    avg_sell_price=Decimal("0"),
                ),
            ),
            top_sellers=(
                BrokerTransaction(
                    broker_code="CC",
                    broker_name="CC",
                    broker_type=BrokerType.LOCAL,
                    buy_lot=0,
                    sell_lot=50,
                    buy_value=Decimal("0"),
                    sell_value=Decimal("500"),
                    avg_buy_price=Decimal("0"),
                    avg_sell_price=Decimal("10"),
                ),
            ),
            foreign_buy_value=Decimal("1000"),
            foreign_sell_value=Decimal("500"),
            foreign_buy_lot=100,
            foreign_sell_lot=50,
            total_value=Decimal("10000"),
            total_lot=1000,
            source="stockbit",
        ),
    ])

    result = runner.invoke(
        app,
        [
            "view", "ticker", "top-brokers", "BBCA",
            "--date", "2026-06-12", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Tracked brokers" not in result.stdout
    assert "ZP" in result.stdout
    assert "CC" in result.stdout


def test_old_view_broker_top_ticker_path_is_gone():
    result = runner.invoke(app, ["view", "broker", "top", "BBCA"])
    assert result.exit_code != 0


def test_view_ticker_distribution_empty(monkeypatch, tmp_path: Path):
    provider = MagicMock()
    provider.get_distribution.return_value = None
    monkeypatch.setattr(
        "src.adapters.cli.view_ticker_distribution_commands.create_broker_distribution_provider",
        lambda db_path: provider,
    )
    result = runner.invoke(
        app,
        ["view", "ticker", "distribution", "BBCA", "--db", str(tmp_path / "x.db")],
    )
    assert result.exit_code == 1
    assert "No cached broker distribution for BBCA" in result.stdout
    assert "Run: saham fetch market BBCA" in result.stdout


def test_view_ticker_top_brokers_json_envelope(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    repo = SQLiteBrokerRepository(db_path)
    d = date(2026, 6, 12)
    repo.save_broker_summaries([
        BrokerSummary(
            ticker="BBCA",
            date=d,
            top_buyers=(
                BrokerTransaction(
                    broker_code="ZP",
                    broker_name="ZP",
                    broker_type=BrokerType.FOREIGN,
                    buy_lot=100,
                    sell_lot=0,
                    buy_value=Decimal("1000"),
                    sell_value=Decimal("0"),
                    avg_buy_price=Decimal("10"),
                    avg_sell_price=Decimal("0"),
                ),
            ),
            top_sellers=(),
            foreign_buy_value=Decimal("1000"),
            foreign_sell_value=Decimal("0"),
            foreign_buy_lot=100,
            foreign_sell_lot=0,
            total_value=Decimal("10000"),
            total_lot=1000,
            source="stockbit",
        ),
    ])
    result = runner.invoke(
        app,
        [
            "view", "ticker", "top-brokers", "BBCA",
            "--date", "2026-06-12", "--format", "json", "--db", str(db_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verb"] == "top-brokers"
    assert payload["status"] == "ok"
    assert payload["source"] == "summary"
    assert payload["scope"] == "full"
    assert payload["data"]["top_buyers"][0]["broker_code"] == "ZP"
