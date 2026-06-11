"""
AccumulationScreenUseCase — multi-stock foreign accumulation screener.

Scans a list of tickers for sustained foreign investor accumulation
patterns. Scores each ticker using a composite signal:
  - Net buy consistency (% of days with net foreign buying)
  - Consecutive buy streak
  - Foreign VWAP vs current price (are foreigners underwater?)
  - RSI (is there still upside room?)

Intraday vs Swing usage:
  This screener produces a SWING WATCHLIST (5–20 day horizon).
  For intraday timing, cross-reference with `saham screen pre-open`.

Layer: Application
Depends on: Domain ports only — no infrastructure imports
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository

SHARES_PER_LOT = 100

# Known institutional/foreign broker codes on IDX
INSTITUTIONAL_BROKERS = {"CS", "AK", "BK", "ZP", "MS", "DB", "RX", "ML", "YU"}


@dataclass
class AccumulationScreenRequest:
    """Input parameters for the screener."""

    tickers: list[str]
    window_days: int = 7           # analysis window: 7, 30, or 90
    min_net_buy_days: int = 2      # skip tickers with fewer qualifying days
    min_score: float = 0.0         # filter: only include scores >= this
    rsi_period: int = 14
    sma_period: int = 20


@dataclass
class AccumulationCandidate:
    """Screener result for a single ticker."""

    ticker: str
    window_days: int
    net_buy_days: int              # days with positive net foreign value
    total_days: int                # total days with broker data in window
    net_buy_ratio: float           # net_buy_days / total_days (0–1)
    total_net_value: Decimal       # cumulative net foreign IDR
    consecutive_streak: int        # current run of consecutive buy days
    foreign_vwap: Decimal | None   # volume-weighted avg foreign buy price
    current_price: Decimal         # latest close price
    vwap_discount_pct: float | None  # (vwap - price) / price * 100
                                     # positive = foreigners are underwater
    rsi: float | None
    trend: str                     # "UP" | "DOWN" | "SIDE"
    score: float                   # 0–100 composite score
    top_brokers: list[str] | None  # per-broker codes (Stockbit only)
    institutional_flag: bool       # True if major institutional broker present

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "window_days": self.window_days,
            "net_buy_days": self.net_buy_days,
            "total_days": self.total_days,
            "net_buy_ratio": round(self.net_buy_ratio, 4),
            "total_net_value": str(self.total_net_value),
            "consecutive_streak": self.consecutive_streak,
            "foreign_vwap": str(self.foreign_vwap) if self.foreign_vwap else None,
            "current_price": str(self.current_price),
            "vwap_discount_pct": round(self.vwap_discount_pct, 2) if self.vwap_discount_pct is not None else None,
            "rsi": round(self.rsi, 2) if self.rsi else None,
            "trend": self.trend,
            "score": self.score,
            "top_brokers": self.top_brokers,
            "institutional_flag": self.institutional_flag,
        }


@dataclass
class AccumulationScreenResponse:
    """Screener output."""

    candidates: list[AccumulationCandidate]   # sorted by score descending
    screened_at: date
    window_days: int
    total_tickers_checked: int
    tickers_skipped: int           # insufficient data
    provider: str                  # "idx" or "stockbit"


def _score(candidate: AccumulationCandidate) -> float:
    """Composite score 0–100 (105 with institutional bonus).

    Weights:
      40 pts — net buy ratio (consistency)
      30 pts — consecutive streak (capped at 10 days)
      20 pts — foreign VWAP > current price (foreigners underwater = floor)
      10 pts — RSI < 50 (room to run, not overbought)
       5 pts — institutional broker present (Stockbit only)
    """
    s = 0.0
    s += candidate.net_buy_ratio * 40.0
    s += min(candidate.consecutive_streak / 10.0, 1.0) * 30.0
    if candidate.vwap_discount_pct is not None and candidate.vwap_discount_pct > 0:
        s += 20.0
    if candidate.rsi is not None and candidate.rsi < 50:
        s += 10.0
    if candidate.institutional_flag:
        s += 5.0
    return round(s, 1)


class AccumulationScreenUseCase:
    """
    Scan multiple tickers for foreign accumulation patterns.

    Reads from local repositories only — no network calls.
    All data must be fetched beforehand via `saham update`.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository

    def execute(
        self, request: AccumulationScreenRequest
    ) -> AccumulationScreenResponse:
        today = date.today()
        window_start = today - timedelta(days=request.window_days + 30)
        # +30 days buffer for RSI/SMA warmup

        candidates: list[AccumulationCandidate] = []
        skipped = 0
        uses_stockbit = False

        for ticker in request.tickers:
            result = self._evaluate_ticker(
                ticker=ticker,
                window_days=request.window_days,
                window_start=window_start,
                today=today,
                min_net_buy_days=request.min_net_buy_days,
                rsi_period=request.rsi_period,
                sma_period=request.sma_period,
            )

            if result is None:
                skipped += 1
                continue

            if result.top_brokers is not None:
                uses_stockbit = True

            result.score = _score(result)
            if result.score >= request.min_score:
                candidates.append(result)

        candidates.sort(key=lambda c: c.score, reverse=True)

        return AccumulationScreenResponse(
            candidates=candidates,
            screened_at=today,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=skipped,
            provider="stockbit" if uses_stockbit else "idx",
        )

    def _evaluate_ticker(
        self,
        ticker: str,
        window_days: int,
        window_start: date,
        today: date,
        min_net_buy_days: int,
        rsi_period: int,
        sma_period: int,
    ) -> AccumulationCandidate | None:
        """Compute accumulation metrics for one ticker."""
        # Load broker data for the window
        summaries = self._broker_repo.get_broker_summaries(
            ticker=ticker,
            start_date=window_start,
            end_date=today,
        )

        if not summaries:
            return None

        # Restrict to exact window
        cutoff = today - timedelta(days=window_days)
        window_summaries = [s for s in summaries if s.date > cutoff]

        if len(window_summaries) < min_net_buy_days:
            return None

        # Core accumulation metrics
        net_buy_days = sum(1 for s in window_summaries if s.is_foreign_accumulating)
        total_days = len(window_summaries)
        net_buy_ratio = net_buy_days / total_days if total_days > 0 else 0.0
        total_net_value = sum(
            (s.foreign_net_value for s in window_summaries), Decimal("0")
        )

        # Consecutive buy streak (counting backwards from most recent)
        streak = 0
        for s in sorted(window_summaries, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        # Foreign VWAP
        total_buy_value = sum(
            (s.foreign_buy_value for s in window_summaries), Decimal("0")
        )
        total_buy_lots = sum(s.foreign_buy_lot for s in window_summaries)
        foreign_vwap: Decimal | None = None
        if total_buy_lots > 0:
            try:
                foreign_vwap = (
                    total_buy_value / (total_buy_lots * SHARES_PER_LOT)
                ).quantize(Decimal("0.01"))
            except InvalidOperation:
                foreign_vwap = None

        # Load candles for price + RSI + trend
        candles = self._market_repo.get_candles(ticker)
        if not candles:
            current_price = Decimal("0")
            rsi = None
            trend = "SIDE"
        else:
            current_price = candles[-1].close
            rsi = self._compute_rsi(candles, rsi_period)
            trend = self._compute_trend(candles, sma_period)

        # VWAP discount %
        vwap_discount_pct: float | None = None
        if foreign_vwap is not None and current_price > 0:
            try:
                vwap_discount_pct = float(
                    (foreign_vwap - current_price) / current_price * 100
                )
            except (InvalidOperation, ZeroDivisionError):
                pass

        # Granular broker info (Stockbit only — top_buyers is non-empty)
        top_brokers: list[str] | None = None
        institutional_flag = False

        # Use the most recent summary that has broker detail
        for s in sorted(window_summaries, key=lambda x: x.date, reverse=True):
            if s.top_buyers:
                top_brokers = [b.broker_code for b in s.top_buyers[:5] if b.is_net_buyer]
                institutional_flag = any(
                    b.broker_code in INSTITUTIONAL_BROKERS
                    for b in s.top_buyers
                    if b.is_net_buyer
                )
                break

        return AccumulationCandidate(
            ticker=ticker,
            window_days=window_days,
            net_buy_days=net_buy_days,
            total_days=total_days,
            net_buy_ratio=net_buy_ratio,
            total_net_value=total_net_value,
            consecutive_streak=streak,
            foreign_vwap=foreign_vwap,
            current_price=current_price,
            vwap_discount_pct=vwap_discount_pct,
            rsi=rsi,
            trend=trend,
            score=0.0,  # set after by _score()
            top_brokers=top_brokers,
            institutional_flag=institutional_flag,
        )

    def _compute_rsi(self, candles: list, period: int) -> float | None:
        """Simple RSI computation from candles."""
        closes = [float(c.close) for c in candles]
        if len(closes) < period + 1:
            return None

        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))

        # Initial averages (SMA seed)
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing for the rest
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _compute_trend(self, candles: list, sma_period: int) -> str:
        """Classify trend relative to SMA."""
        if len(candles) < sma_period:
            return "SIDE"

        recent = candles[-sma_period:]
        sma = sum(float(c.close) for c in recent) / sma_period
        current = float(candles[-1].close)
        pct_diff = (current - sma) / sma * 100

        if pct_diff > 2.0:
            return "UP"
        elif pct_diff < -2.0:
            return "DOWN"
        return "SIDE"
