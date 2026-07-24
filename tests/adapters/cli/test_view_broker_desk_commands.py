"""CLI tests for desk-centric view broker commands."""

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
    repo.save_broker_daily_flows([
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
    ])


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
