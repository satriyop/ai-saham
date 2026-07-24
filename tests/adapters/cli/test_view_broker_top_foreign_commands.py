"""Tests for view broker top-foreign (universe cache)."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.broker_flow import ForeignFlowSnapshot
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

runner = CliRunner()


def test_view_broker_top_foreign_reads_cached_snapshots_only(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    snapshot_date = date(2024, 1, 16)
    repo = SQLiteBrokerRepository(db_path)
    repo.save_foreign_flow_snapshots(
        [
            ForeignFlowSnapshot(
                ticker="BBCA",
                date=snapshot_date,
                net_val=Decimal("1500000000"),
                net_lot=1500,
            ),
            ForeignFlowSnapshot(
                ticker="BBRI",
                date=snapshot_date,
                net_val=Decimal("-500000000"),
                net_lot=-500,
            ),
        ],
        snapshot_date=snapshot_date,
        period_days=7,
    )

    result = runner.invoke(
        app,
        [
            "view",
            "broker",
            "top-foreign",
            "--date",
            "2024-01-16",
            "--days",
            "7",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Cached Foreign Broker Top Stocks" in result.stdout
    assert "BBCA" in result.stdout
    assert "BBRI" in result.stdout


def test_view_broker_top_foreign_json_output_stays_machine_readable(tmp_path: Path):
    db_path = tmp_path / "broker.db"
    snapshot_date = date(2024, 1, 16)
    repo = SQLiteBrokerRepository(db_path)
    repo.save_foreign_flow_snapshots(
        [
            ForeignFlowSnapshot(
                ticker="BBCA",
                date=snapshot_date,
                net_val=Decimal("1500000000"),
                net_lot=1500,
            ),
        ],
        snapshot_date=snapshot_date,
        period_days=7,
    )

    result = runner.invoke(
        app,
        [
            "view",
            "broker",
            "top-foreign",
            "--date",
            "2024-01-16",
            "--days",
            "7",
            "--format",
            "json",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == [
        {
            "ticker": "BBCA",
            "snapshot_date": "2024-01-16",
            "period_days": 7,
            "net_val": "1500000000",
            "net_lot": 1500,
            "direction": "buy",
        }
    ]
