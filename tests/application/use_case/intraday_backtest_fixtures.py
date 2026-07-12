from datetime import date, timedelta
from decimal import Decimal

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


class InMemoryMarketRepository(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = list(candles)

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
        rng = self.get_date_range(ticker)
        return bool(rng and rng[0] <= start_date and rng[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        candles = self.get_candles(ticker)
        if not candles:
            return None
        return candles[0].date, candles[-1].date


class InMemoryBrokerRepository(BrokerDataRepository):
    def __init__(self, summaries: list[BrokerSummary] | None = None) -> None:
        self._summaries = list(summaries or [])

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self._summaries.append(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self._summaries.extend(summaries)

    def get_broker_summary(
        self, ticker: str, target_date: date
    ) -> BrokerSummary | None:
        for s in self._summaries:
            if s.ticker == ticker.upper() and s.date == target_date:
                return s
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
        rng = self.get_date_range(ticker)
        return bool(rng and rng[0] <= start_date and rng[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class StubIndicatorRegistry(IndicatorRegistry):
    def __init__(
        self,
        atr: Decimal | None = Decimal("2"),
        rsi: Decimal | None = Decimal("50"),
        sma: Decimal | None = Decimal("99"),
    ) -> None:
        super().__init__()
        self._atr = atr
        self._rsi = rsi
        self._sma = sma

    def compute(
        self,
        name: str,
        candles: list[Candle],
        period: int,
        price_field: str = "close",
    ):
        if not candles:
            return []
        last_date = candles[-1].date
        n = name.upper()
        if n == "ATR":
            return [(last_date, self._atr)] if self._atr is not None else []
        if n == "RSI":
            return [(last_date, self._rsi)] if self._rsi is not None else []
        if n == "SMA":
            return [(last_date, self._sma)] if self._sma is not None else []
        return []


def _candle(
    ticker: str,
    day: date,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
    )


def _flat(ticker: str, day: date, price: Decimal) -> Candle:
    return _candle(ticker, day, price, price, price, price)


def _history(
    ticker: str,
    end_day: date,
    days: int = 30,
    base_price: Decimal = Decimal("100"),
) -> list[Candle]:
    candles = []
    for i in range(days):
        day = end_day - timedelta(days=days - 1 - i)
        candles.append(_flat(ticker, day, base_price))
    return candles


def _history_with_prev(
    ticker: str,
    prev_day: date,
    prev_close: Decimal = Decimal("100"),
    prev_high: Decimal = Decimal("105"),
    prev_low: Decimal = Decimal("98"),
    days: int = 30,
) -> list[Candle]:
    candles = _history(ticker, prev_day - timedelta(days=1), days=days - 1, base_price=prev_close)
    candles.append(_candle(ticker, prev_day, prev_close, prev_high, prev_low, prev_close))
    return candles


def _backed_summaries(
    ticker: str, end_day: date, days: int = 7
) -> list[BrokerSummary]:
    out = []
    for i in range(days):
        day = end_day - timedelta(days=days - 1 - i)
        out.append(BrokerSummary(
            ticker=ticker,
            date=day,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("1000000"),
            foreign_sell_value=Decimal("100000"),
            foreign_buy_lot=10_000,
            foreign_sell_lot=1_000,
            total_value=Decimal("2000000"),
            total_lot=20_000,
        ))
    return out


PREV_DAY = date(2026, 6, 9)
TRADE_DAY = date(2026, 6, 10)
TICKER = "BBCA"


def _default_request(**overrides) -> IntradayBacktestRequest:
    base = {
        "tickers": [TICKER],
        "start_date": TRADE_DAY,
        "end_date": TRADE_DAY,
        "capital": Decimal("100000000"),
        "risk_pct": Decimal("0.01"),
        "max_daily_positions": 3,
        "cost_bps": Decimal("0"),
        "history_days": 30,
    }
    base.update(overrides)
    return IntradayBacktestRequest(**base)


def _build(
    today_candle: Candle,
    *,
    ticker: str = TICKER,
    history: list[Candle] | None = None,
    summaries: list[BrokerSummary] | None = None,
    registry: IndicatorRegistry | None = None,
) -> IntradayBacktestUseCase:
    hist = history if history is not None else _history_with_prev(ticker, PREV_DAY)
    market = InMemoryMarketRepository(hist + [today_candle])
    default_sums = _backed_summaries(ticker, PREV_DAY)
    broker = InMemoryBrokerRepository(
        summaries if summaries is not None else default_sums
    )
    reg = registry if registry is not None else StubIndicatorRegistry()
    return IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=reg,
    )
