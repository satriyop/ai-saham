"""Tests for MarketFreshnessService — cache-tolerance policy, no infrastructure."""

from datetime import date

from src.application.services.market_freshness_service import (
    BenchmarkTickerAliases,
    MarketFreshnessService,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository

ALIASES = BenchmarkTickerAliases(canonical="IHSG", legacy="^JKSE")


class FakeMarketDataRepository(MarketDataRepository):
    def __init__(self, date_ranges: dict[str, tuple[date, date]] | None = None) -> None:
        self._date_ranges = date_ranges or {}

    def save_candles(self, candles: list[Candle]) -> None:
        raise NotImplementedError

    def get_candles(self, ticker, start_date=None, end_date=None) -> list[Candle]:
        raise NotImplementedError

    def has_data(self, ticker, start_date, end_date) -> bool:
        raise NotImplementedError

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        return self._date_ranges.get(ticker)


def test_last_known_trading_day_uses_canonical_benchmark():
    repo = FakeMarketDataRepository({"IHSG": (date(2026, 1, 1), date(2026, 6, 19))})
    service = MarketFreshnessService(repository=repo)

    assert service.last_known_trading_day(ALIASES) == date(2026, 6, 19)


def test_last_known_trading_day_falls_back_to_legacy_alias():
    repo = FakeMarketDataRepository({"^JKSE": (date(2026, 1, 1), date(2026, 6, 10))})
    service = MarketFreshnessService(repository=repo)

    assert service.last_known_trading_day(ALIASES) == date(2026, 6, 10)


def test_last_known_trading_day_returns_none_on_first_run():
    repo = FakeMarketDataRepository({})
    service = MarketFreshnessService(repository=repo)

    assert service.last_known_trading_day(ALIASES) is None


def test_resolve_reference_trading_day_falls_back_to_last_weekday_when_uncached():
    repo = FakeMarketDataRepository({})
    service = MarketFreshnessService(repository=repo)

    # Saturday 2026-06-20 -> Friday 2026-06-19
    assert service.resolve_reference_trading_day(ALIASES, date(2026, 6, 20)) == date(2026, 6, 19)


def test_end_tolerance_days_uses_weekday_fallback_for_benchmark_itself():
    repo = FakeMarketDataRepository({"IHSG": (date(2026, 1, 1), date(2020, 1, 1))})
    service = MarketFreshnessService(repository=repo)

    # is_benchmark=True must ignore stale cached data and use weekday fallback,
    # to avoid the circular dependency where benchmark candles use their own
    # stale data to decide if they need updating.
    tolerance = service.end_tolerance_days(
        is_benchmark=True, benchmark=ALIASES, today=date(2026, 6, 15)
    )
    assert tolerance == 0


def test_end_tolerance_days_computed_from_cached_reference_day_for_other_tickers():
    repo = FakeMarketDataRepository({"IHSG": (date(2026, 1, 1), date(2026, 6, 10))})
    service = MarketFreshnessService(repository=repo)

    tolerance = service.end_tolerance_days(
        is_benchmark=False, benchmark=ALIASES, today=date(2026, 6, 15)
    )
    assert tolerance == 5


def test_end_tolerance_days_never_negative():
    repo = FakeMarketDataRepository({"IHSG": (date(2026, 1, 1), date(2026, 6, 15))})
    service = MarketFreshnessService(repository=repo)

    tolerance = service.end_tolerance_days(
        is_benchmark=False, benchmark=ALIASES, today=date(2026, 6, 15)
    )
    assert tolerance == 0
