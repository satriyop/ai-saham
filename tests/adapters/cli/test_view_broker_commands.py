"""Tests for read-only broker browsing commands."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.broker_flow import ForeignFlowPoint, ForeignFlowSnapshot
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

runner = CliRunner()


def test_view_broker_history_reads_cached_points_only(monkeypatch, tmp_path: Path):
    from src.adapters.cli import broker_commands

    def fail_provider_factory(provider_name: str):
        raise AssertionError(f"provider should not be created: {provider_name}")

    monkeypatch.setattr(broker_commands, "_create_provider", fail_provider_factory)

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
        ["view", "broker", "history", "BBCA", "--days", "2", "--source", "stockbit", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Cached Foreign Flow History for BBCA" in result.stdout
    assert "2024-01-15" in result.stdout
    assert "2024-01-16" in result.stdout


def test_view_broker_top_foreign_reads_cached_snapshots_only(monkeypatch, tmp_path: Path):
    from src.adapters.cli import broker_commands

    def fail_provider_factory(provider_name: str):
        raise AssertionError(f"provider should not be created: {provider_name}")

    monkeypatch.setattr(broker_commands, "_create_provider", fail_provider_factory)

    db_path = tmp_path / "broker.db"
    snapshot_date = date(2024, 1, 16)
    repo = SQLiteBrokerRepository(db_path)
    repo.save_foreign_flow_snapshots(
        [
            ForeignFlowSnapshot(
                ticker="BBCA",
                date=snapshot_date,
                net_val=Decimal("1000000"),
                net_lot=100,
            ),
            ForeignFlowSnapshot(
                ticker="BBRI",
                date=snapshot_date,
                net_val=Decimal("-500000"),
                net_lot=-50,
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
            snapshot_date.isoformat(),
            "--days",
            "7",
            "--limit",
            "2",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Cached Foreign Broker Top Stocks" in result.stdout
    assert "BBCA" in result.stdout
    assert "BBRI" in result.stdout
