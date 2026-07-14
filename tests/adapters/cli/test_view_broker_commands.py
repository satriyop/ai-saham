"""Tests for read-only broker browsing commands."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.broker_flow import ForeignFlowPoint, ForeignFlowSnapshot
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

runner = CliRunner()


def test_view_broker_history_reads_cached_points_only(tmp_path: Path):
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
            "view", "broker", "history", "BBCA",
            "--days", "2", "--source", "stockbit", "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Cached Foreign Flow History for BBCA" in result.stdout
    assert "2024-01-15" in result.stdout
    assert "2024-01-16" in result.stdout


def test_view_broker_history_json_output_stays_machine_readable(tmp_path: Path):
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
            "view",
            "broker",
            "history",
            "BBCA",
            "--source",
            "stockbit",
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
            "date": "2024-01-15",
            "source": "stockbit",
            "net_val": "1000000",
            "net_lot": 100,
            "avg_price": "10000",
        }
    ]


def test_view_broker_top_foreign_reads_cached_snapshots_only(tmp_path: Path):
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


def test_view_broker_top_foreign_json_output_stays_machine_readable(tmp_path: Path):
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
            "net_val": "1000000",
            "net_lot": 100,
            "direction": "buy",
        }
    ]


def test_broker_distribution_no_cache_exits_with_error(monkeypatch, tmp_path: Path):
    from unittest.mock import MagicMock

    mock_provider = MagicMock()
    mock_provider.get_distribution.return_value = None
    monkeypatch.setattr(
        "src.adapters.cli.view_broker_distribution_commands.create_broker_distribution_provider",
        lambda db_path: mock_provider,
    )
    result = runner.invoke(
        app,
        ["view", "broker", "distribution", "BBCA", "--db", str(tmp_path / "x.db")],
    )
    assert result.exit_code == 1
    assert "No broker distribution data cached for BBCA" in result.stdout


def test_broker_distribution_display_renders_snapshot(capsys):
    from src.adapters.cli.view_broker_distribution_display import (
        display_broker_distribution,
    )
    from src.domain.value_objects.broker_distribution import (
        BrokerCounterparty,
        BrokerDistributionEntry,
        BrokerDistributionSnapshot,
    )

    snapshot = BrokerDistributionSnapshot(
        ticker="BBCA",
        date=date(2024, 1, 15),
        top_buyers=(
            BrokerDistributionEntry(
                broker_code="YU",
                broker_type="Asing",
                amount_idr=100_000_000_000,
                counterparties=(
                    BrokerCounterparty(
                        broker_code="MG", broker_type="Lokal", amount_idr=60_000_000_000,
                    ),
                    BrokerCounterparty(
                        broker_code="AK", broker_type="Asing", amount_idr=40_000_000_000,
                    ),
                ),
            ),
        ),
        top_sellers=(
            BrokerDistributionEntry(
                broker_code="ZP",
                broker_type="Lokal",
                amount_idr=50_000_000_000,
                counterparties=(
                    BrokerCounterparty(
                        broker_code="AG", broker_type="Asing", amount_idr=30_000_000_000,
                    ),
                ),
            ),
        ),
    )

    display_broker_distribution(snapshot)
    captured = capsys.readouterr()
    assert "BBCA" in captured.out
    assert "Broker Distribution" in captured.out
    assert "YU[A]" in captured.out
    assert "100.0B" in captured.out
    assert "MG[L]" in captured.out
    assert "TOP BUYERS" in captured.out
    assert "TOP SELLERS" in captured.out


def test_broker_status_active_session(monkeypatch):
    from unittest.mock import MagicMock

    mock_session = MagicMock()
    mock_session.authenticated = True
    monkeypatch.setattr(
        "src.infrastructure.composition.stockbit_session_factory.get_stockbit_session",
        lambda: mock_session,
    )
    result = runner.invoke(app, ["view", "broker", "status"])
    assert result.exit_code == 0
    assert "Active" in result.stdout


def test_broker_status_no_session(monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.composition.stockbit_session_factory.get_stockbit_session",
        lambda: None,
    )
    result = runner.invoke(app, ["view", "broker", "status"])
    assert result.exit_code == 0
    assert "No session" in result.stdout
