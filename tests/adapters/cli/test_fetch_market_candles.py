import re
from datetime import date
from pathlib import Path

import pytest

from src.adapters.cli.fetch_market_candle_refresh import fetch_candles
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from tests.adapters.cli.fetch_market_command_fixtures import (
    FakeMarketProvider,
    _candle,
    _generate_candles,
)


def test_fetch_candles_uses_stockbit_historical_for_benchmark_with_stockbit(
    monkeypatch,
    tmp_path: Path,
):
    db_path = tmp_path / "data.db"

    class FakeStockbitHistoricalProvider:
        provider_name = "stockbit"
        volume_unit = "shares"
        price_adjustment_policy = "raw"
        instances: list["FakeStockbitHistoricalProvider"] = []

        def __init__(self, api_client, non_idx_tickers=None) -> None:
            self.api_client = api_client
            self.requested: list[tuple[str, date, date]] = []
            self.instances.append(self)

        def fetch_daily_ohlcv(self, ticker: str, start_date: date, end_date: date):
            self.requested.append((ticker, start_date, end_date))
            return [_candle("IHSG", start_date)]

    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_candle_refresh.StockbitHistoricalProvider",
        FakeStockbitHistoricalProvider,
    )

    class _FakeBroker:
        api_client = object()

    status = fetch_candles(
        ticker="^JKSE",
        days=1,
        db_path=db_path,
        provider_name="yahoo",
        refresh=True,
        broker_provider=_FakeBroker(),
    )

    repo = SQLiteMarketRepository(db_path)
    rows = repo.get_candles("IHSG")
    assert status.startswith("+")
    assert len(rows) == 1
    assert rows[0].ticker == "IHSG"
    assert FakeStockbitHistoricalProvider.instances[0].requested[0][0] == "IHSG"


def test_fetch_candles_backfills_older_gap(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteMarketRepository(db_path)
    today = date.today()
    cached_start = date.fromordinal(today.toordinal() - 90)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_candles(_generate_candles("BBCA", cached_start, today))
    class _FakeBroker:
        api_client = object()

    FakeMarketProvider.instances.clear()
    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_candle_refresh.StockbitHistoricalProvider",
        FakeMarketProvider,
    )
    notes: list[str] = []

    status = fetch_candles(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=False,
        short_history=notes,
        broker_provider=_FakeBroker(),
    )

    assert status.startswith("backfill+")
    assert FakeMarketProvider.instances[0].requested_ranges == [
        (requested_start, date.fromordinal(cached_start.toordinal() - 1))
    ]
    assert notes == [
        f"  candles BBCA: 90d cached (from {cached_start}), "
        "requested 365d - backfilling older gap"
    ]


def test_fetch_candles_treats_small_leading_non_trading_gap_as_current(
    monkeypatch,
    tmp_path: Path,
):
    db_path = tmp_path / "data.db"
    repo = SQLiteMarketRepository(db_path)
    today = date.today()
    requested_start = date.fromordinal(today.toordinal() - 365)
    cached_start = date.fromordinal(requested_start.toordinal() + 2)
    repo.save_candles(_generate_candles("BBCA", cached_start, today))
    class _FakeBroker:
        api_client = object()

    FakeMarketProvider.instances.clear()
    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_candle_refresh.StockbitHistoricalProvider",
        FakeMarketProvider,
    )
    notes: list[str] = []

    status = fetch_candles(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=False,
        short_history=notes,
        broker_provider=_FakeBroker(),
    )

    assert status.startswith("✓(")
    assert FakeMarketProvider.instances[0].requested_ranges == []
    assert notes == []


def test_fetch_candles_treats_recent_trading_day_as_current(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteMarketRepository(db_path)
    today = date.today()
    latest = date.fromordinal(today.toordinal() - 2)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_candles(_generate_candles("BBCA", requested_start, latest) + [
        _candle("IHSG", latest),
    ])
    class _FakeBroker:
        api_client = object()

    FakeMarketProvider.instances.clear()
    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_candle_refresh.StockbitHistoricalProvider",
        FakeMarketProvider,
    )

    status = fetch_candles(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=False,
        broker_provider=_FakeBroker(),
    )

    assert status.startswith("✓(")
    assert FakeMarketProvider.instances[0].requested_ranges == []


def test_fetch_candles_requires_stockbit_session_for_regular_idx_ticker(tmp_path: Path):
    from src.application.use_case.resolve_candle_provider_policy_use_case import (
        STOCKBIT_SESSION_REQUIRED_ERROR,
    )

    with pytest.raises(ValueError, match=re.escape(STOCKBIT_SESSION_REQUIRED_ERROR)):
        fetch_candles(
            ticker="BBCA",
            days=90,
            db_path=tmp_path / "data.db",
            provider_name="yahoo",
            refresh=False,
            broker_provider=None,
        )


def test_fetch_market_command_fails_fast_when_stockbit_session_missing(monkeypatch, tmp_path: Path):
    from typer import Typer
    from typer.testing import CliRunner

    from src.adapters.cli.fetch_market_commands import fetch_market
    from src.application.use_case.resolve_candle_provider_policy_use_case import (
        STOCKBIT_SESSION_REQUIRED_ERROR,
    )

    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_commands.create_broker_provider",
        lambda name: (object(), "idx"),
    )
    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_commands.resolve_tickers",
        lambda **kwargs: ["BBCA"],
    )

    app = Typer()
    app.command()(fetch_market)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "BBCA",
            "--provider", "yahoo",
            "--no-meta",
            "--no-enrichment",
            "--db", str(tmp_path / "data.db"),
        ],
    )

    assert result.exit_code == 1
    assert f"Error: {STOCKBIT_SESSION_REQUIRED_ERROR}" in result.output
    assert "Updating" not in result.output
