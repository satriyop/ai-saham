"""
AccumulationScreenUseCase — multi-stock foreign accumulation screener.

Scans a list of tickers for sustained foreign investor accumulation
patterns. Scores each ticker using a composite signal:
  - Net buy consistency (% of days with net foreign buying)
  - Consecutive buy streak (exponential, uncapped)
  - Foreign VWAP vs current price (are foreigners underwater?)
  - RSI headroom (tent function peaking at RSI=40)
  - Avg foreign flow ratio (% of daily turnover that's foreign)
  - Bollinger Band squeeze (coiled spring detection)

Intraday vs Swing usage:
  This screener produces a SWING WATCHLIST (5–20 day horizon).
  For intraday timing, cross-reference with `saham intraday pre-open`.

Layer: Application
Depends on: Domain ports only — no infrastructure imports
"""

import math
from dataclasses import dataclass, field
from datetime import date
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
    window_days: int = 7           # latest broker sessions: 7, 30, or 90
    min_net_buy_days: int = 2      # skip tickers with fewer qualifying days
    min_score: float = 0.0         # filter: only include scores >= this
    rsi_period: int = 14
    sma_period: int = 20
    as_of_date: date | None = None # deterministic replay date; defaults to today


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
    score: float                   # 0–120 composite score
    top_brokers: list[str] | None  # per-broker codes (Stockbit only)
    institutional_flag: bool       # True if major institutional broker present
    # Improvement #1: flow ratio signal
    avg_flow_ratio: float | None = None   # avg % of daily turnover that's foreign
    score_breakdown: dict = field(default_factory=dict)  # per-component pts
    # Improvement #3: BB squeeze
    bb_width: float | None = None         # current BB Width %
    bb_width_pctile: float | None = None  # 0..1 vs last 60 days (lower = tighter)

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
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "trend": self.trend,
            "score": self.score,
            "top_brokers": self.top_brokers,
            "institutional_flag": self.institutional_flag,
            "avg_flow_ratio": round(self.avg_flow_ratio, 2) if self.avg_flow_ratio is not None else None,
            "score_breakdown": self.score_breakdown,
            "bb_width": round(self.bb_width, 2) if self.bb_width is not None else None,
            "bb_width_pctile": round(self.bb_width_pctile, 3) if self.bb_width_pctile is not None else None,
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


def _score(candidate: AccumulationCandidate) -> tuple[float, dict]:
    """Composite score 0–120 (soft cap).

    Weights:
      40 pts — net buy ratio (consistency)
      30 pts — consecutive streak (exponential, τ=7d, uncapped)
      20 pts — VWAP discount (linear 0..10% → 0..20 pts)
      10 pts — RSI headroom (tent peak at RSI=40, zero at ≤25 or ≥75)
      10 pts — avg foreign flow ratio (% of daily turnover, saturates at 20%)
      10 pts — BB Width squeeze (bottom 20th pctile vs last 60d)
       5 pts — institutional broker present (Stockbit only)
    """
    # Consistency: 0..40
    s_consistency = candidate.net_buy_ratio * 40.0

    # Streak: soft exponential saturation, τ=7d — 7d≈63%, 14d≈86%, never caps
    s_streak = 30.0 * (1.0 - math.exp(-candidate.consecutive_streak / 7.0))

    # VWAP discount: linear ramp, saturates at 10% underwater
    d = candidate.vwap_discount_pct or 0.0
    s_vwap = max(0.0, min(d, 10.0)) / 10.0 * 20.0

    # RSI: tent function peaking at 40 (room to run without panic)
    rsi = candidate.rsi
    if rsi is None:
        s_rsi = 5.0          # neutral when data missing
    elif rsi <= 25 or rsi >= 75:
        s_rsi = 0.0
    elif rsi <= 40:
        s_rsi = (rsi - 25) / 15.0 * 10.0
    else:
        s_rsi = (75.0 - rsi) / 35.0 * 10.0

    # Avg flow ratio: % of daily turnover that's net foreign
    fr = max(0.0, min(candidate.avg_flow_ratio or 0.0, 20.0))
    s_flow = fr / 20.0 * 10.0

    # Institutional flag
    s_inst = 5.0 if candidate.institutional_flag else 0.0

    # BB squeeze: low percentile rank = tighter band = coiled spring
    pctile = candidate.bb_width_pctile
    if pctile is None:
        s_squeeze = 0.0
    elif pctile <= 0.20:
        s_squeeze = 10.0 - pctile / 0.20 * 5.0   # 10..5 pts
    elif pctile <= 0.40:
        s_squeeze = 5.0 - (pctile - 0.20) / 0.20 * 5.0  # 5..0 pts
    else:
        s_squeeze = 0.0

    total = round(
        min(s_consistency + s_streak + s_vwap + s_rsi + s_flow + s_inst + s_squeeze, 120.0),
        1,
    )
    breakdown = {
        "cons": round(s_consistency, 1),
        "streak": round(s_streak, 1),
        "vwap": round(s_vwap, 1),
        "rsi": round(s_rsi, 1),
        "flow": round(s_flow, 1),
        "bb": round(s_squeeze, 1),
        "inst": round(s_inst, 1),
    }
    return total, breakdown


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
        today = request.as_of_date or date.today()
        candidates: list[AccumulationCandidate] = []
        skipped = 0
        uses_stockbit = False

        for ticker in request.tickers:
            result = self._evaluate_ticker(
                ticker=ticker,
                window_days=request.window_days,
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

            result.score, result.score_breakdown = _score(result)
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
        today: date,
        min_net_buy_days: int,
        rsi_period: int,
        sma_period: int,
    ) -> AccumulationCandidate | None:
        """Compute accumulation metrics for one ticker."""
        # Load all broker rows up to as_of_date, then select the latest N
        # broker sessions. Calendar-day cutoffs distort IDX windows around
        # weekends, holidays, and data-lag days.
        summaries = self._broker_repo.get_broker_summaries(
            ticker=ticker,
            start_date=None,
            end_date=today,
        )

        if not summaries:
            return None

        window_summaries = sorted(summaries, key=lambda s: s.date)[-window_days:]

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

        # Avg foreign flow ratio (% of total daily turnover, already in BrokerSummary)
        flow_ratios = [
            float(s.foreign_flow_ratio)
            for s in window_summaries
            if s.total_value > 0
        ]
        avg_flow_ratio = sum(flow_ratios) / len(flow_ratios) if flow_ratios else None

        # Load candles for price + RSI + trend + BB squeeze
        candles = self._market_repo.get_candles(ticker, end_date=today)
        if not candles:
            current_price = Decimal("0")
            rsi = None
            trend = "SIDE"
            bb_width = None
            bb_width_pctile = None
        else:
            current_price = candles[-1].close
            rsi = self._compute_rsi(candles, rsi_period)
            trend = self._compute_trend(candles, sma_period)
            bb_width, bb_width_pctile = self._compute_bb_squeeze(candles)

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
            avg_flow_ratio=avg_flow_ratio,
            bb_width=bb_width,
            bb_width_pctile=bb_width_pctile,
        )

    def _compute_rsi(self, candles: list, period: int) -> float | None:
        """Wilder's RSI from candle close prices."""
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

    @staticmethod
    def _compute_bb_widths(candles: list, period: int = 20) -> list[float]:
        """BB Width = (upper - lower) / mid * 100 for each candle."""
        closes = [float(c.close) for c in candles]
        if len(closes) < period:
            return []
        out = []
        for i in range(period - 1, len(closes)):
            window = closes[i - period + 1: i + 1]
            mid = sum(window) / period
            if mid <= 0:
                out.append(0.0)
                continue
            std = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
            out.append(4.0 * std / mid * 100)  # (upper-lower)/mid*100, upper=mid+2σ
        return out

    def _compute_bb_squeeze(
        self, candles: list, period: int = 20, history: int = 60
    ) -> tuple[float | None, float | None]:
        """Return (bb_width_now, percentile_rank_vs_last_N_days).

        percentile=0.0 means current width is the tightest in `history` days
        (maximum squeeze). percentile=1.0 means widest (expanding volatility).
        """
        widths = self._compute_bb_widths(candles, period)
        if not widths:
            return None, None
        bb_width_now = widths[-1]
        if len(widths) < history:
            return bb_width_now, None
        recent = widths[-history:]
        rank = sum(1 for w in recent if w <= bb_width_now) / len(recent)
        return bb_width_now, rank
