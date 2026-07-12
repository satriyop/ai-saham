from datetime import date
from decimal import Decimal
from pathlib import Path

from src.adapters.cli.fetch_market_broker_refresh import fetch_broker
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from tests.adapters.cli.fetch_market_command_fixtures import (
    EchoLatestBrokerProvider,
    FakeBrokerProvider,
    _candle,
    _summary,
)


def test_fetch_broker_skips_index_ticker(tmp_path: Path):
    result = fetch_broker(
        ticker="IHSG",
        days=90,
        db_path=tmp_path / "data.db",
        broker_provider=object(),
        refresh=False,
    )

    assert result.summaries == "n/a:index"
    assert result.flow == "n/a:index"


def test_fetch_broker_skips_legacy_index_alias(tmp_path: Path):
    result = fetch_broker(
        ticker="^JKSE",
        days=90,
        db_path=tmp_path / "data.db",
        broker_provider=object(),
        refresh=False,
    )

    assert result.summaries == "n/a:index"
    assert result.flow == "n/a:index"


def test_fetch_broker_backfills_older_summary_gap(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    cached_start = date.fromordinal(today.toordinal() - 90)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_broker_summary(_summary("BBCA", cached_start, "idx"))
    repo.save_broker_summary(_summary("BBCA", today, "idx"))
    provider = FakeBrokerProvider("idx")

    result = fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=provider,
        refresh=False,
    )

    assert result.summaries.startswith("backfill+")
    assert provider.requested_ranges == [
        (requested_start, date.fromordinal(cached_start.toordinal() - 1))
    ]


def test_fetch_broker_uses_flow_points_for_stockbit_session_coverage(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    flow_start = date.fromordinal(today.toordinal() - 90)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=flow_start,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        ),
        ForeignFlowPoint(
            ticker="BBCA",
            date=today,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        ),
    ])
    historical_points = [
        ForeignFlowPoint(
            ticker="BBCA",
            date=requested_start,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        )
    ]
    stockbit_provider = FakeBrokerProvider("stockbit", historical_points=historical_points)
    idx_provider = FakeBrokerProvider("idx")

    result = fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=stockbit_provider,
        refresh=False,
        _idx_summary_provider=idx_provider,
    )

    assert result.summaries.startswith("+")
    assert idx_provider.requested_ranges == [
        (requested_start, today)
    ]
    assert repo.get_foreign_flow_date_range("BBCA", source="stockbit") == (
        requested_start,
        today,
    )


def test_fetch_broker_treats_recent_trading_day_as_current(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    latest = date.fromordinal(today.toordinal() - 2)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_broker_summary(_summary("BBCA", requested_start, "idx"))
    repo.save_broker_summary(_summary("BBCA", latest, "idx"))
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=requested_start,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        ),
        ForeignFlowPoint(
            ticker="BBCA",
            date=latest,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        ),
    ])
    market_repo = SQLiteMarketRepository(db_path)
    market_repo.save_candles([_candle("IHSG", latest)])
    provider = FakeBrokerProvider("stockbit")

    result = fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=provider,
        refresh=False,
    )

    assert result.summaries.startswith("✓(")
    assert result.flow.startswith("agg=✓(")
    assert provider.requested_ranges == []


def test_fetch_broker_counts_only_new_local_dates(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    latest = date.fromordinal(today.toordinal() - 10)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_broker_summary(_summary("BBCA", requested_start, "idx"))
    repo.save_broker_summary(_summary("BBCA", latest, "idx"))
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=latest,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        )
    ])
    stockbit_provider = FakeBrokerProvider("stockbit")
    idx_provider = EchoLatestBrokerProvider("idx", echo_date=latest)

    result = fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=stockbit_provider,
        refresh=False,
        _idx_summary_provider=idx_provider,
    )

    assert result.summaries == f"up-to-date({latest.isoformat()})"
    assert result.flow == f"agg=✓({latest.isoformat()})"
    assert idx_provider.requested_ranges == [
        (date.fromordinal(latest.toordinal() + 1), today)
    ]
