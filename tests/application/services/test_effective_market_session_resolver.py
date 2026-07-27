"""Tests for EffectiveMarketSessionResolver — canonical IDX session policy."""

from datetime import date, datetime

import pytest

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.benchmark_symbol import BenchmarkTickerAliases
from src.domain.value_objects.idx_market import IDX_TIMEZONE

ALIASES = BenchmarkTickerAliases(canonical="IHSG", legacy="^JKSE")


def _candle(ticker: str, on: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=on,
        open=100,
        high=110,
        low=90,
        close=105,
        volume=1000,
    )


class FakeMarketDataRepository(MarketDataRepository):
    def __init__(self, candle_dates: dict[str, list[date]] | None = None) -> None:
        self._candles = {
            ticker: [_candle(ticker, d) for d in sorted(dates)]
            for ticker, dates in (candle_dates or {}).items()
        }

    def save_candles(self, candles: list[Candle]) -> None:
        raise NotImplementedError

    def get_candles(self, ticker, start_date=None, end_date=None) -> list[Candle]:
        rows = self._candles.get(ticker, [])
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        return rows

    def has_data(self, ticker, start_date, end_date) -> bool:
        raise NotImplementedError

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self._candles.get(ticker, [])
        if not rows:
            return None
        return rows[0].date, rows[-1].date


def _wib(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IDX_TIMEZONE)


# Monday 2026-06-15 .. Friday 2026-06-19 are regular IDX trading sessions
# in these fixtures; 2026-06-20/21 is a weekend.


def test_weekday_before_market_close_uses_prior_completed_session():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(run_at=_wib(2026, 6, 19, 10, 0))

    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.is_eod_pending is True
    assert result.resolution_source == "ihsg_cache_prior_session"
    assert result.market_session_name == "REGULAR"


def test_weekday_after_market_close_uses_cached_same_day_ihsg():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 18), date(2026, 6, 19)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(run_at=_wib(2026, 6, 19, 17, 0))

    assert result.latest_completed_session == date(2026, 6, 19)
    assert result.is_eod_pending is False
    assert result.resolution_source == "ihsg_cache_same_day"
    assert result.market_session_name == "AFTER_CLOSE"


def test_weekday_after_market_close_with_stale_ihsg_cache_keeps_latest_cached_session():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(run_at=_wib(2026, 6, 19, 17, 0))

    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.is_eod_pending is False
    assert result.resolution_source == "ihsg_cache_stale_or_holiday"
    assert result.notes
    assert "2026-06-18" in result.notes[0]


def test_weekend_uses_latest_cached_ihsg_session():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 18), date(2026, 6, 19)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    # Saturday 2026-06-20.
    result = resolver.resolve(run_at=_wib(2026, 6, 20, 12, 0))

    assert result.latest_completed_session == date(2026, 6, 19)
    assert result.market_session_name == "WEEKEND"
    assert result.is_eod_pending is False
    assert result.resolution_source == "ihsg_cache_weekend"


def test_public_holiday_like_weekday_uses_latest_cached_ihsg_session_not_weekday_fallback():
    # 2026-06-19 (Friday) is a holiday: no IHSG session that day, cache stops
    # at 2026-06-18 even though 2026-06-19 is a weekday and would blindly
    # resolve to itself under naive weekday-only logic.
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(run_at=_wib(2026, 6, 19, 17, 0))

    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.resolution_source == "ihsg_cache_stale_or_holiday"


def test_missing_ihsg_cache_falls_back_to_weekday_logic_with_explicit_source_and_notes():
    repo = FakeMarketDataRepository({})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(run_at=_wib(2026, 6, 19, 17, 0))

    assert result.latest_completed_session == date(2026, 6, 19)
    assert result.resolution_source == "weekday_fallback_post_close"
    assert result.notes


def test_decision_at_overrides_run_at():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 18), date(2026, 6, 19)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(
        run_at=_wib(2026, 6, 25, 10, 0),
        decision_at=_wib(2026, 6, 19, 17, 0),
    )

    assert result.decision_at == _wib(2026, 6, 19, 17, 0)
    assert result.latest_completed_session == date(2026, 6, 19)
    assert result.resolution_source == "ihsg_cache_same_day"


def test_naive_datetime_is_rejected():
    repo = FakeMarketDataRepository({})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    with pytest.raises(ValueError):
        resolver.resolve(run_at=datetime(2026, 6, 19, 10, 0))


def test_naive_decision_at_is_rejected():
    repo = FakeMarketDataRepository({})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    with pytest.raises(ValueError):
        resolver.resolve(
            run_at=_wib(2026, 6, 19, 10, 0),
            decision_at=datetime(2026, 6, 19, 10, 0),
        )


def test_before_open_resolves_distinctly_from_regular_session():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    # 08:00, before PRE_OPEN_START (08:45).
    result = resolver.resolve(run_at=_wib(2026, 6, 19, 8, 0))

    assert result.market_session_name == "BEFORE_OPEN"
    assert result.market_session_name != "REGULAR"
    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.is_eod_pending is True


def test_pre_open_resolves_to_pre_open():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    # 08:50, within the pre-open call auction (08:45-09:00).
    result = resolver.resolve(run_at=_wib(2026, 6, 19, 8, 50))

    assert result.market_session_name == "PRE_OPEN"
    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.is_eod_pending is True


def test_regular_session_resolves_to_regular():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    # 10:00, continuous trading.
    result = resolver.resolve(run_at=_wib(2026, 6, 19, 10, 0))

    assert result.market_session_name == "REGULAR"
    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.is_eod_pending is True


def test_pre_closing_resolves_to_pre_closing():
    repo = FakeMarketDataRepository({"IHSG": [date(2026, 6, 17), date(2026, 6, 18)]})
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    # 15:55, within the pre-closing call auction (15:50-16:00).
    result = resolver.resolve(run_at=_wib(2026, 6, 19, 15, 55))

    assert result.market_session_name == "PRE_CLOSING"
    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.is_eod_pending is True


def test_bounded_ihsg_lookup_does_not_leak_future_cached_sessions():
    # Cache already has a future session (e.g. an audit run today with data
    # fetched ahead), but decision_at is a past date — must not leak it.
    repo = FakeMarketDataRepository(
        {"IHSG": [date(2026, 6, 17), date(2026, 6, 18), date(2026, 6, 25)]}
    )
    resolver = EffectiveMarketSessionResolver(repo, benchmark=ALIASES)

    result = resolver.resolve(run_at=_wib(2026, 6, 19, 17, 0))

    assert result.latest_completed_session == date(2026, 6, 18)
    assert result.latest_completed_session < date(2026, 6, 25)
