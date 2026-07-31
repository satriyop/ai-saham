"""Unit tests for PIT tradable-universe membership."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.application.services.pit_tradable_membership import (
    resolve_pit_tradable_membership,
    session_window_start,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository


def _candle(ticker: str, on: date, close: int = 100) -> Candle:
    price = Decimal(close)
    return Candle(
        ticker=ticker,
        date=on,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1000,
    )


class FakeMarketRepository(MarketDataRepository):
    def __init__(self, candles: dict[str, list[Candle]]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        raise NotImplementedError

    def get_candles(self, ticker, start_date=None, end_date=None):
        rows = list(self._candles.get(ticker.upper(), self._candles.get(ticker, [])))
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker, start_date, end_date) -> bool:
        return bool(self.get_candles(ticker, start_date, end_date))

    def get_date_range(self, ticker: str):
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date

    def list_tickers_with_candles_between(self, start_date, end_date):
        if start_date > end_date:
            return []
        found: set[str] = set()
        for ticker, rows in self._candles.items():
            for candle in rows:
                if start_date <= candle.date <= end_date:
                    found.add(ticker.upper())
                    break
        return sorted(found)


def _mon_fri_sessions(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


class TestSessionWindowStart:
    def test_inclusive_n_sessions_ending_at_as_of(self):
        sessions = _mon_fri_sessions(date(2026, 7, 1), 15)
        as_of = sessions[10]
        start = session_window_start(sessions, as_of, 5)
        assert start == sessions[6]
        # inclusive: sessions[6]..sessions[10] is 5 sessions
        assert sessions.index(as_of) - sessions.index(start) + 1 == 5

    def test_as_of_not_session_returns_none(self):
        sessions = _mon_fri_sessions(date(2026, 7, 1), 10)
        assert session_window_start(sessions, date(2026, 7, 4), 5) is None  # Saturday

    def test_thin_history_uses_available(self):
        sessions = _mon_fri_sessions(date(2026, 7, 1), 3)
        as_of = sessions[-1]
        assert session_window_start(sessions, as_of, 10) == sessions[0]

    def test_window_sessions_must_be_positive(self):
        import pytest

        with pytest.raises(ValueError):
            session_window_start([date(2026, 7, 1)], date(2026, 7, 1), 0)


class TestResolvePitTradableMembership:
    def test_delist_mid_window_inclusion_boundary(self):
        # 12 weekday sessions starting Mon 2026-07-06
        sessions = _mon_fri_sessions(date(2026, 7, 6), 12)
        last_live = sessions[4]  # DELI last candle
        # IHSG present on all sessions
        ihsg = [_candle("IHSG", d) for d in sessions]
        deli = [_candle("DELI", d) for d in sessions if d <= last_live]
        live = [_candle("LIVE", d) for d in sessions]
        repo = FakeMarketRepository(
            {
                "IHSG": ihsg,
                "DELI": deli,
                "LIVE": live,
            }
        )

        # as_of = last_live → DELI still in window (N=3)
        members = resolve_pit_tradable_membership(
            as_of_date=last_live,
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        assert "DELI" in members
        assert "LIVE" in members

        # as_of three sessions after last_live with N=3 → DELI excluded
        # window is sessions[end-2:end+1] ending at sessions[7] if last_live is sessions[4]
        as_of_after = sessions[4 + 3]  # first session fully past the N=3 window
        members_after = resolve_pit_tradable_membership(
            as_of_date=as_of_after,
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        assert "DELI" not in members_after
        assert "LIVE" in members_after

        # as_of just one session after last_live with N=3 → still included
        as_of_near = sessions[5]
        members_near = resolve_pit_tradable_membership(
            as_of_date=as_of_near,
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        assert "DELI" in members_near

    def test_named_intersection(self):
        sessions = _mon_fri_sessions(date(2026, 7, 6), 5)
        as_of = sessions[-1]
        repo = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "BBCA": [_candle("BBCA", d) for d in sessions],
                "OUTSIDE": [_candle("OUTSIDE", d) for d in sessions],
            }
        )
        members = resolve_pit_tradable_membership(
            as_of_date=as_of,
            window_sessions=5,
            market_repository=repo,
            named_tickers=["BBCA", "MISSING"],
        )
        assert members == ("BBCA",)

    def test_cached_board_includes_any_active_equity(self):
        sessions = _mon_fri_sessions(date(2026, 7, 6), 5)
        as_of = sessions[-1]
        repo = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "ZZZZ": [_candle("ZZZZ", d) for d in sessions],
            }
        )
        members = resolve_pit_tradable_membership(
            as_of_date=as_of,
            window_sessions=5,
            market_repository=repo,
            named_tickers=None,
        )
        assert members == ("ZZZZ",)

    def test_benchmark_filtered(self):
        sessions = _mon_fri_sessions(date(2026, 7, 6), 3)
        as_of = sessions[-1]
        repo = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "^JKSE": [_candle("^JKSE", d) for d in sessions],
                "BBCA": [_candle("BBCA", d) for d in sessions],
            }
        )
        members = resolve_pit_tradable_membership(
            as_of_date=as_of,
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        assert members == ("BBCA",)

    def test_as_of_not_session_returns_empty(self):
        sessions = _mon_fri_sessions(date(2026, 7, 6), 5)
        repo = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "BBCA": [_candle("BBCA", d) for d in sessions],
            }
        )
        members = resolve_pit_tradable_membership(
            as_of_date=date(2026, 7, 11),  # Saturday
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        assert members == ()

    def test_deterministic_sorted(self):
        sessions = _mon_fri_sessions(date(2026, 7, 6), 3)
        as_of = sessions[-1]
        repo = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "TLKM": [_candle("TLKM", d) for d in sessions],
                "BBCA": [_candle("BBCA", d) for d in sessions],
                "ASII": [_candle("ASII", d) for d in sessions],
            }
        )
        a = resolve_pit_tradable_membership(
            as_of_date=as_of,
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        b = resolve_pit_tradable_membership(
            as_of_date=as_of,
            window_sessions=3,
            market_repository=repo,
            named_tickers=None,
        )
        assert a == b == ("ASII", "BBCA", "TLKM")
