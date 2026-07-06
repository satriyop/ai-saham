"""Tests for cache-aware market data refresh use case."""

from datetime import date
from decimal import Decimal

import pytest

from src.application.use_case.refresh_market_data_use_case import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import MarketDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository


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


class FakeMarketProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.requested_ranges: list[tuple[date, date]] = []
        self.provider_name = "fake"
        self.volume_unit = "shares"
        self.price_adjustment_policy = "raw"

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        self.requested_ranges.append((start_date, end_date))
        return [_candle(ticker, start_date)]


class EmptyMarketProvider(FakeMarketProvider):
    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        self.requested_ranges.append((start_date, end_date))
        return []


class MemoryMarketRepository(MarketDataRepository):
    def __init__(self) -> None:
        self._storage: dict[str, list[Candle]] = {}
        self.saved_metadata: list[dict[str, str]] = []

    def save_candles(
        self,
        candles: list[Candle],
        **metadata: str,
    ) -> None:
        if metadata:
            self.saved_metadata.append(metadata)
        for candle in candles:
            ticker = candle.ticker.upper()
            existing = [
                c for c in self._storage.get(ticker, []) if c.date != candle.date
            ]
            existing.append(candle)
            existing.sort(key=lambda c: c.date)
            self._storage[ticker] = existing

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        candles = list(self._storage.get(ticker.upper(), []))
        if start_date is not None:
            candles = [c for c in candles if c.date >= start_date]
        if end_date is not None:
            candles = [c for c in candles if c.date <= end_date]
        return candles

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        cached_range = self.get_date_range(ticker)
        return bool(
            cached_range
            and cached_range[0] <= start_date
            and cached_range[1] >= end_date
        )

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        candles = self.get_candles(ticker)
        if not candles:
            return None
        return candles[0].date, candles[-1].date


def test_refresh_backfills_older_gap_without_refetching_current_data():
    repo = MemoryMarketRepository()
    provider = FakeMarketProvider()
    end_date = date(2026, 6, 14)
    cached_start = date(2026, 3, 16)
    requested_start = date(2025, 6, 14)
    repo.save_candles([
        _candle("BBCA", cached_start),
        _candle("BBCA", end_date),
    ])

    response = RefreshMarketDataUseCase(provider, repo).execute(
        RefreshMarketDataRequest(
            ticker="BBCA",
            days=365,
            end_date=end_date,
        )
    )

    assert response.status.startswith("backfill+")
    assert provider.requested_ranges == [
        (requested_start, date(2026, 3, 15))
    ]
    assert response.short_history_note == (
        "  candles BBCA: 90d cached (from 2026-03-16), "
        "requested 365d - backfilling older gap"
    )


def test_refresh_treats_small_start_gap_as_cached_current():
    repo = MemoryMarketRepository()
    provider = FakeMarketProvider()
    end_date = date(2026, 6, 14)
    repo.save_candles([
        _candle("BBCA", date(2025, 6, 16)),
        _candle("BBCA", end_date),
    ])

    response = RefreshMarketDataUseCase(provider, repo).execute(
        RefreshMarketDataRequest(
            ticker="BBCA",
            days=365,
            end_date=end_date,
        )
    )

    assert response.status == "cached-current"
    assert provider.requested_ranges == []
    assert response.short_history_note is None


def test_refresh_reports_up_to_date_when_provider_adds_no_new_rows():
    repo = MemoryMarketRepository()
    provider = EmptyMarketProvider()
    end_date = date(2026, 6, 14)
    latest = date(2026, 6, 1)
    repo.save_candles([
        _candle("BBCA", date(2025, 6, 14)),
        _candle("BBCA", latest),
    ])

    response = RefreshMarketDataUseCase(provider, repo).execute(
        RefreshMarketDataRequest(
            ticker="BBCA",
            days=365,
            end_date=end_date,
        )
    )

    assert response.status == "up-to-date(2026-06-01)"
    assert provider.requested_ranges == [(date(2026, 6, 1), end_date)]


def test_refresh_passes_provider_metadata_when_repository_supports_it():
    repo = MemoryMarketRepository()
    provider = FakeMarketProvider()
    end_date = date(2026, 6, 14)

    RefreshMarketDataUseCase(provider, repo).execute(
        RefreshMarketDataRequest(
            ticker="BBCA",
            days=30,
            end_date=end_date,
        )
    )

    assert repo.saved_metadata == [
        {
            "source": "fake",
            "volume_unit": "shares",
            "price_adjustment_policy": "raw",
        }
    ]


def test_refresh_rejects_empty_ticker():
    repo = MemoryMarketRepository()
    provider = FakeMarketProvider()

    with pytest.raises(ValueError, match="Ticker cannot be empty"):
        RefreshMarketDataUseCase(provider, repo).execute(
            RefreshMarketDataRequest(ticker=" ", days=30)
        )


def test_refresh_forward_fill_includes_latest_to_overwrite_partial_candle():
    repo = MemoryMarketRepository()
    provider = FakeMarketProvider()
    end_date = date(2026, 6, 14)
    latest = date(2026, 6, 13)

    # Save a partial/pre-market candle for June 13
    repo.save_candles([
        _candle("BBCA", date(2026, 6, 1)),
        _candle("BBCA", latest),
    ])

    RefreshMarketDataUseCase(provider, repo).execute(
        RefreshMarketDataRequest(
            ticker="BBCA",
            days=2,
            end_date=end_date,
            end_tolerance_days=0,
        )
    )

    # Verify that the forward fill range starts on `latest` (June 13)
    # instead of `latest + 1` (June 14) to overwrite partial quotes
    assert provider.requested_ranges == [(latest, end_date)]

