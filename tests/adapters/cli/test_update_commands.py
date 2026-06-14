"""Tests for update command helper behavior."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.adapters.cli.update_commands import (
    _broker_update_status,
    _cached_status,
    _fetch_candles,
    _fetch_broker,
    _is_cached_status,
    _no_new_data_status,
    _range_update_status,
)
from src.domain.entities.candle import Candle
from src.domain.entities.broker_flow import ForeignFlowPoint, BrokerSummary
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository


def _candle(ticker: str, day: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("100"),
        volume=1000,
    )


def _summary(ticker: str, day: date, source: str = "idx") -> BrokerSummary:
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source=source,
    )


class FakeBrokerProvider:
    def __init__(
        self,
        provider_name: str = "idx",
        historical_points: list[ForeignFlowPoint] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.historical_points = historical_points or []
        self.requested_ranges: list[tuple[date, date]] = []

    def is_authenticated(self) -> bool:
        return True

    def fetch_broker_summary(self, ticker: str, target_date: date):
        return _summary(ticker, target_date, self.provider_name)

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        self.requested_ranges.append((start_date, end_date))
        return [_summary(ticker, start_date, self.provider_name)]

    def fetch_foreign_flow_history(
        self,
        ticker: str,
        days: int = 365,
    ) -> list[ForeignFlowPoint]:
        return self.historical_points


class EchoLatestBrokerProvider(FakeBrokerProvider):
    def __init__(self, provider_name: str = "stockbit", echo_date: date | None = None) -> None:
        super().__init__(provider_name)
        self.echo_date = echo_date

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        self.requested_ranges.append((start_date, end_date))
        return [_summary(ticker, self.echo_date or end_date, self.provider_name)]


class FakeMarketProvider:
    instances: list["FakeMarketProvider"] = []

    def __init__(self) -> None:
        self.requested_ranges: list[tuple[date, date]] = []
        FakeMarketProvider.instances.append(self)

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        self.requested_ranges.append((start_date, end_date))
        return [_candle(ticker, start_date)]


def test_cached_status_reports_exact_cache_age():
    assert _cached_status(date(2026, 6, 13), date(2026, 6, 13)) == "cached-current"


def test_is_cached_status_matches_explicit_cache_statuses():
    assert _is_cached_status("cached-current") is True
    assert _is_cached_status("provider-no-new-data(latest=2026-06-10)") is False
    assert _is_cached_status("+2d") is False
    assert _is_cached_status("ERR:timeout") is False


def test_no_new_data_status_reports_provider_check_result():
    assert (
        _no_new_data_status(date(2026, 6, 10))
        == "up-to-date(2026-06-10)"
    )
    assert _no_new_data_status(None) == "no-data"


def test_broker_update_status_distinguishes_rows_from_calendar_span():
    assert _broker_update_status(
        added_count=11,
        updated_range=(date(2025, 6, 14), date(2026, 6, 14)),
        fetch_modes={"backfill"},
    ) == "backfill+11rows/span=366d"
    assert _broker_update_status(0, None, {"initial"}) == "no-data"


def test_range_update_status_distinguishes_rows_from_calendar_span():
    assert _range_update_status(
        added_count=11,
        updated_range=(date(2025, 6, 14), date(2026, 6, 14)),
        fetch_modes={"backfill"},
    ) == "backfill+11rows/span=366d"
    assert _range_update_status(0, None, {"initial"}) == "no-data"


def test_fetch_broker_skips_index_ticker(tmp_path: Path):
    status = _fetch_broker(
        ticker="^JKSE",
        days=90,
        db_path=tmp_path / "data.db",
        broker_provider=object(),
        refresh=False,
    )

    assert status == "n/a:index"


def test_fetch_candles_backfills_older_gap(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteMarketRepository(db_path)
    today = date.today()
    cached_start = date.fromordinal(today.toordinal() - 90)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_candles([
        _candle("BBCA", cached_start),
        _candle("BBCA", today),
    ])
    FakeMarketProvider.instances.clear()
    monkeypatch.setattr(
        "src.adapters.cli.update_commands.YahooFinanceProvider",
        FakeMarketProvider,
    )
    notes: list[str] = []

    status = _fetch_candles(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=False,
        short_history=notes,
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
    repo.save_candles([
        _candle("BBCA", cached_start),
        _candle("BBCA", today),
    ])
    FakeMarketProvider.instances.clear()
    monkeypatch.setattr(
        "src.adapters.cli.update_commands.YahooFinanceProvider",
        FakeMarketProvider,
    )
    notes: list[str] = []

    status = _fetch_candles(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=False,
        short_history=notes,
    )

    assert status == "cached-current"
    assert FakeMarketProvider.instances[0].requested_ranges == []
    assert notes == []


def test_fetch_candles_treats_recent_trading_day_as_current(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteMarketRepository(db_path)
    today = date.today()
    latest = date.fromordinal(today.toordinal() - 2)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_candles([
        _candle("BBCA", requested_start),
        _candle("BBCA", latest),
    ])
    FakeMarketProvider.instances.clear()
    monkeypatch.setattr(
        "src.adapters.cli.update_commands.YahooFinanceProvider",
        FakeMarketProvider,
    )

    status = _fetch_candles(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=False,
    )

    assert status == "cached-current"
    assert FakeMarketProvider.instances[0].requested_ranges == []


def test_fetch_broker_backfills_older_summary_gap(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    cached_start = date.fromordinal(today.toordinal() - 90)
    requested_start = date.fromordinal(today.toordinal() - 365)
    repo.save_broker_summary(_summary("BBCA", cached_start, "idx"))
    repo.save_broker_summary(_summary("BBCA", today, "idx"))
    provider = FakeBrokerProvider("idx")

    status = _fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=provider,
        refresh=False,
    )

    assert status.startswith("backfill+")
    assert provider.requested_ranges == [
        (requested_start, date.fromordinal(cached_start.toordinal() - 1))
    ]


def test_fetch_broker_uses_flow_points_for_stockbit_session_coverage(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    flow_start = date.fromordinal(today.toordinal() - 90)
    requested_start = date.fromordinal(today.toordinal() - 365)
    # Only stockbit flow_points exist — IDX summaries have no coverage.
    # The backfill range should be derived from flow_points coverage, not summaries.
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

    status = _fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=stockbit_provider,
        refresh=False,
        _idx_summary_provider=idx_provider,
    )

    assert status.startswith("backfill+")
    # Backfill range is determined by flow_points coverage, sent to IDX for summaries
    assert idx_provider.requested_ranges == [
        (requested_start, date.fromordinal(flow_start.toordinal() - 1))
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
    repo.save_broker_summary(_summary("BBCA", requested_start, "stockbit"))
    repo.save_broker_summary(_summary("BBCA", latest, "stockbit"))
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
    provider = FakeBrokerProvider("stockbit")

    status = _fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=provider,
        refresh=False,
    )

    assert status == "cached-current"
    assert provider.requested_ranges == []


def test_fetch_broker_counts_only_new_local_dates(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    today = date.today()
    latest = date.fromordinal(today.toordinal() - 10)
    requested_start = date.fromordinal(today.toordinal() - 365)
    # Seed IDX summaries (broker_summaries always come from IDX now)
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
    # IDX provider echoes back 'latest' so no new dates are added (up-to-date path)
    idx_provider = EchoLatestBrokerProvider("idx", echo_date=latest)

    status = _fetch_broker(
        ticker="BBCA",
        days=365,
        db_path=db_path,
        broker_provider=stockbit_provider,
        refresh=False,
        _idx_summary_provider=idx_provider,
    )

    assert status == f"up-to-date({latest.isoformat()})"
    assert idx_provider.requested_ranges == [
        (date.fromordinal(latest.toordinal() + 1), today)
    ]
