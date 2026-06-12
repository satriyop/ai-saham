"""Tests for deterministic market regime analysis."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeUseCase,
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
        candles = self.get_candles(ticker)
        if not candles:
            return None
        return candles[0].date, candles[-1].date


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


def _summary(ticker: str, day: date, positive: bool = True) -> BrokerSummary:
    buy_value = Decimal("100000000")
    sell_value = Decimal("0") if positive else Decimal("200000000")
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=buy_value,
        foreign_sell_value=sell_value,
        foreign_buy_lot=10_000,
        foreign_sell_lot=0 if positive else 20_000,
        total_value=Decimal("300000000"),
        total_lot=30_000,
    )


def test_market_regime_labels_bullish_when_benchmark_and_breadth_are_strong():
    base = date(2026, 1, 1)
    as_of = base + timedelta(days=59)
    candles = [
        _candle("^JKSE", base + timedelta(days=i), Decimal(1000 + i))
        for i in range(60)
    ]
    candles.extend(
        _candle("BBCA", base + timedelta(days=i), Decimal(100 + i))
        for i in range(60)
    )
    candles.extend(
        _candle("BBRI", base + timedelta(days=i), Decimal(200 + i))
        for i in range(60)
    )
    summaries = [
        _summary("BBCA", as_of, positive=True),
        _summary("BBRI", as_of, positive=True),
    ]
    use_case = MarketRegimeUseCase(
        market_repository=MockMarketRepository(candles),
        broker_repository=MockBrokerRepository(summaries),
    )

    response = use_case.execute(MarketRegimeRequest(
        universe=["BBCA", "BBRI"],
        benchmark_ticker="^JKSE",
        as_of_date=as_of,
    ))

    assert response.label == "BULLISH"
    assert response.score == 7
    assert response.breadth_above_sma20_pct == 100.0
    assert response.foreign_flow_breadth_pct == 100.0


def test_market_regime_warns_when_benchmark_is_missing():
    base = date(2026, 1, 1)
    candles = [
        _candle("BBCA", base + timedelta(days=i), Decimal(100 + i))
        for i in range(30)
    ]
    use_case = MarketRegimeUseCase(
        market_repository=MockMarketRepository(candles),
        broker_repository=MockBrokerRepository([]),
    )

    response = use_case.execute(MarketRegimeRequest(
        universe=["BBCA"],
        benchmark_ticker="^JKSE",
        as_of_date=base + timedelta(days=29),
    ))

    assert response.benchmark_close is None
    assert response.warnings
