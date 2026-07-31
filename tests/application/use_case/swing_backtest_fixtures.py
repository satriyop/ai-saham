from datetime import date, timedelta
from decimal import Decimal

from src.application.ports.rules_loader import RulesLoader
from src.application.use_case.assess_risk_use_case import AssessRiskResponse
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


class FakeRulesLoader(RulesLoader):
    """Minimal RulesLoader stand-in for tests that require the constructor
    parameter but never exercise real YAML parsing."""

    def load(self, path=None, registry=None):
        raise NotImplementedError(
            "FakeRulesLoader does not parse rules — inject a real loader "
            "if this test needs strategy evidence to actually resolve"
        )

    def load_from_string(self, content, registry=None, source_name="<generated>"):
        raise NotImplementedError(
            "FakeRulesLoader does not parse rules — inject a real loader "
            "if this test needs strategy evidence to actually resolve"
        )


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


class FakeRiskEngine:
    def __init__(self) -> None:
        self.contexts = []
        self.as_of_dates = []

    def assess_with_context(self, ticker, gate_context, market_context=None, as_of_date=None):
        self.contexts.append(gate_context)
        self.as_of_dates.append(as_of_date)
        assessment = RiskAssessment(
            rationale=("all gates passed",),
            snapshot_date=gate_context.snapshot_date,
            indicators=IndicatorSnapshot(
                date=gate_context.snapshot_date,
                sma=Decimal("100"),
                ema=Decimal("100"),
                rsi=Decimal("50"),
            ),
        )
        return AssessRiskResponse(
            ticker=ticker,
            assessment=assessment,
            sma_period=20,
            ema_period=20,
            rsi_period=14,
        )


class FailingRiskEngine:
    def assess_with_context(self, ticker, gate_context, market_context=None, as_of_date=None):
        raise ValueError("missing attribution inputs")


def _ohlc(
    ticker: str,
    day: date,
    open_price: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
    )


def _flat_candle(ticker: str, day: date, close: Decimal) -> Candle:
    return _ohlc(ticker, day, close, close, close, close)


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


def _base_candles(ticker: str, base: date) -> list[Candle]:
    candles = [
        _flat_candle(
            ticker,
            base + timedelta(days=i),
            Decimal("100") if i % 2 == 0 else Decimal("101"),
        )
        for i in range(25)
    ]
    candles.append(
        _ohlc(
            ticker,
            base + timedelta(days=25),
            Decimal("100"),
            Decimal("106"),
            Decimal("99"),
            Decimal("105"),
        )
    )
    return candles


class FakeMarketContextProvider:
    def __init__(self, contexts):
        self.contexts = contexts
        self.calls = []

    def evaluate_for_dates(self, *, tickers, replay_dates, benchmark_ticker):
        self.calls.append(
            {
                "tickers": tickers,
                "replay_dates": replay_dates,
                "benchmark_ticker": benchmark_ticker,
            }
        )
        return {
            replay_date: self.contexts[replay_date]
            for replay_date in replay_dates
            if replay_date in self.contexts
        }
