"""
Deterministic market regime analysis for IHSG swing workflows.

Layer: Application
Depends on: Domain ports only
AI usage: None
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class MarketRegimeRequest:
    """Input parameters for market regime analysis."""

    universe: list[str]
    benchmark_ticker: str = "^JKSE"
    as_of_date: date | None = None
    breadth_sma_period: int = 20
    benchmark_sma_fast: int = 20
    benchmark_sma_slow: int = 50
    breadth_lookback_days: int = 5
    foreign_flow_lookback_days: int = 5


@dataclass(frozen=True)
class MarketRegimeResponse:
    """Market regime snapshot for one date."""

    as_of_date: date
    label: str
    score: int
    benchmark_ticker: str
    benchmark_close: Decimal | None
    benchmark_sma20: Decimal | None
    benchmark_sma50: Decimal | None
    benchmark_return_5d_pct: float | None
    benchmark_return_20d_pct: float | None
    breadth_above_sma20_pct: float | None
    breadth_change_5d_pct: float | None
    foreign_flow_breadth_pct: float | None
    universe_count: int
    breadth_count: int
    foreign_flow_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "label": self.label,
            "score": self.score,
            "benchmark_ticker": self.benchmark_ticker,
            "benchmark_close": str(self.benchmark_close) if self.benchmark_close else None,
            "benchmark_sma20": str(self.benchmark_sma20) if self.benchmark_sma20 else None,
            "benchmark_sma50": str(self.benchmark_sma50) if self.benchmark_sma50 else None,
            "benchmark_return_5d_pct": self.benchmark_return_5d_pct,
            "benchmark_return_20d_pct": self.benchmark_return_20d_pct,
            "breadth_above_sma20_pct": self.breadth_above_sma20_pct,
            "breadth_change_5d_pct": self.breadth_change_5d_pct,
            "foreign_flow_breadth_pct": self.foreign_flow_breadth_pct,
            "universe_count": self.universe_count,
            "breadth_count": self.breadth_count,
            "foreign_flow_count": self.foreign_flow_count,
            "warnings": self.warnings,
        }


class MarketRegimeUseCase:
    """
    Compute broad market context for swing trade decisions.

    The score is intentionally simple and inspectable:
      +1 benchmark above SMA20
      +1 benchmark above SMA50
      +1 benchmark 5d return positive
      +1 benchmark 20d return positive
      +1 breadth >= 50%
      +1 breadth change >= 0
      +1 foreign flow breadth >= 50% when available
    """

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository | None = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository

    def execute(self, request: MarketRegimeRequest) -> MarketRegimeResponse:
        tickers = [ticker.upper().strip() for ticker in request.universe if ticker.strip()]
        if not tickers:
            raise ValueError("At least one universe ticker is required")

        as_of = request.as_of_date or date.today()
        warnings: list[str] = []

        benchmark = self._benchmark_metrics(request.benchmark_ticker, as_of, request)
        if benchmark["close"] is None:
            warnings.append(
                f"No benchmark candles for {request.benchmark_ticker}; "
                "regime uses universe breadth only. "
                f"Run: saham fetch market {request.benchmark_ticker} --provider yahoo"
            )

        breadth_now, breadth_count = self._breadth_above_sma(
            tickers,
            as_of,
            request.breadth_sma_period,
        )
        breadth_then, _ = self._breadth_above_sma(
            tickers,
            as_of,
            request.breadth_sma_period,
            latest_before_or_on=True,
        )
        breadth_change = (
            round(breadth_now - breadth_then, 4)
            if breadth_now is not None and breadth_then is not None
            else None
        )

        foreign_breadth, foreign_count = self._foreign_flow_breadth(
            tickers,
            as_of,
            request.foreign_flow_lookback_days,
        )

        score = self._score(
            benchmark_close=benchmark["close"],
            benchmark_sma20=benchmark["sma20"],
            benchmark_sma50=benchmark["sma50"],
            benchmark_return_5d=benchmark["return_5d"],
            benchmark_return_20d=benchmark["return_20d"],
            breadth_now=breadth_now,
            breadth_change=breadth_change,
            foreign_breadth=foreign_breadth,
        )

        return MarketRegimeResponse(
            as_of_date=as_of,
            label=self._label(score),
            score=score,
            benchmark_ticker=request.benchmark_ticker,
            benchmark_close=benchmark["close"],
            benchmark_sma20=benchmark["sma20"],
            benchmark_sma50=benchmark["sma50"],
            benchmark_return_5d_pct=benchmark["return_5d"],
            benchmark_return_20d_pct=benchmark["return_20d"],
            breadth_above_sma20_pct=breadth_now,
            breadth_change_5d_pct=breadth_change,
            foreign_flow_breadth_pct=foreign_breadth,
            universe_count=len(tickers),
            breadth_count=breadth_count,
            foreign_flow_count=foreign_count,
            warnings=warnings,
        )

    def _benchmark_metrics(
        self,
        ticker: str,
        as_of: date,
        request: MarketRegimeRequest,
    ) -> dict:
        candles = self._market_repo.get_candles(
            ticker,
            end_date=as_of,
        )
        if not candles:
            return {
                "close": None,
                "sma20": None,
                "sma50": None,
                "return_5d": None,
                "return_20d": None,
            }

        latest = candles[-1]
        return {
            "close": latest.close,
            "sma20": _sma(candles, request.benchmark_sma_fast),
            "sma50": _sma(candles, request.benchmark_sma_slow),
            "return_5d": _lookback_return(candles, 5),
            "return_20d": _lookback_return(candles, 20),
        }

    def _breadth_above_sma(
        self,
        tickers: list[str],
        as_of: date,
        period: int,
        latest_before_or_on: bool = False,
    ) -> tuple[float | None, int]:
        evaluated = 0
        above = 0
        for ticker in tickers:
            candles = self._market_repo.get_candles(ticker, end_date=as_of)
            if not candles:
                continue
            if latest_before_or_on:
                candles = self._slice_to_prior_trading_day(candles, period)
            if len(candles) < period:
                continue
            sma = _sma(candles, period)
            if sma is None or sma <= 0:
                continue
            evaluated += 1
            if candles[-1].close > sma:
                above += 1

        if evaluated == 0:
            return None, 0
        return round(above / evaluated * 100, 4), evaluated

    def _slice_to_prior_trading_day(
        self,
        candles: list[Candle],
        period: int,
    ) -> list[Candle]:
        if len(candles) <= period + 5:
            return candles
        return candles[:-5]

    def _foreign_flow_breadth(
        self,
        tickers: list[str],
        as_of: date,
        lookback_days: int,
    ) -> tuple[float | None, int]:
        if self._broker_repo is None:
            return None, 0

        start = as_of - timedelta(days=lookback_days + 10)
        evaluated = 0
        positive = 0
        for ticker in tickers:
            summaries = self._broker_repo.get_broker_summaries(
                ticker,
                start_date=start,
                end_date=as_of,
            )
            if not summaries:
                continue
            latest = summaries[-1]
            evaluated += 1
            if latest.foreign_net_value > Decimal("0"):
                positive += 1

        if evaluated == 0:
            return None, 0
        return round(positive / evaluated * 100, 4), evaluated

    def _score(
        self,
        *,
        benchmark_close: Decimal | None,
        benchmark_sma20: Decimal | None,
        benchmark_sma50: Decimal | None,
        benchmark_return_5d: float | None,
        benchmark_return_20d: float | None,
        breadth_now: float | None,
        breadth_change: float | None,
        foreign_breadth: float | None,
    ) -> int:
        score = 0
        if benchmark_close is not None and benchmark_sma20 is not None:
            score += int(benchmark_close > benchmark_sma20)
        if benchmark_close is not None and benchmark_sma50 is not None:
            score += int(benchmark_close > benchmark_sma50)
        if benchmark_return_5d is not None:
            score += int(benchmark_return_5d > 0)
        if benchmark_return_20d is not None:
            score += int(benchmark_return_20d > 0)
        if breadth_now is not None:
            score += int(breadth_now >= 50)
        if breadth_change is not None:
            score += int(breadth_change >= 0)
        if foreign_breadth is not None:
            score += int(foreign_breadth >= 50)
        return score

    @staticmethod
    def _label(score: int) -> str:
        if score >= 6:
            return "BULLISH"
        if score >= 4:
            return "SIDEWAYS"
        if score >= 2:
            return "WEAK"
        return "RISK_OFF"


def _sma(candles: list[Candle], period: int) -> Decimal | None:
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    return sum(closes, Decimal("0")) / Decimal(period)


def _lookback_return(candles: list[Candle], periods: int) -> float | None:
    if len(candles) <= periods:
        return None
    latest = candles[-1].close
    prior = candles[-periods - 1].close
    if prior <= 0:
        return None
    return round(float((latest - prior) / prior * Decimal("100")), 4)
