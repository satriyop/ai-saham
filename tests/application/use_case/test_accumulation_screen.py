"""Tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.accumulation_screen import (
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


class MockMarketRepository(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class MockBrokerRepository(BrokerDataRepository):
    def __init__(self, summaries: list[BrokerSummary]) -> None:
        self._summaries = summaries

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self._summaries.append(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self._summaries.extend(summaries)

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        for summary in self._summaries:
            if summary.ticker == ticker.upper() and summary.date == target_date:
                return summary
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        rows = [s for s in self._summaries if s.ticker == ticker.upper()]
        if start_date is not None:
            rows = [s for s in rows if s.date >= start_date]
        if end_date is not None:
            rows = [s for s in rows if s.date <= end_date]
        return sorted(rows, key=lambda s: s.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


def _candle(ticker: str, day: date, close: Decimal) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
    )


def _summary(ticker: str, day: date, foreign_vwap: Decimal) -> BrokerSummary:
    buy_lot = 10_000
    buy_value = foreign_vwap * Decimal(buy_lot * 100)
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=buy_value,
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=buy_lot,
        foreign_sell_lot=0,
        total_value=buy_value * Decimal("2"),
        total_lot=buy_lot * 2,
    )


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def test_screen_window_uses_latest_broker_sessions_not_calendar_days():
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    candidate = response.candidates[0]
    assert candidate.total_days == 7
    assert candidate.net_buy_days == 7
    assert candidate.consecutive_streak == 7
    assert candidate.window_days == 7
