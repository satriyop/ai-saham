"""
ScreenerCandidate value objects for pre-open screener.

Represents a ticker that passed the IEV filter, together with
computed entry price, stop-loss level, and AI research summary.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MoverData:
    """Raw mover entry from Stockbit pre-open movers list.

    Attributes:
        ticker: IDX ticker symbol (e.g., 'BBCA')
        iev: Intraday External Volume — proxy for institutional interest
    """

    ticker: str
    iev: int


@dataclass(frozen=True)
class OrderBookBid:
    """Best bid from an order book snapshot.

    Attributes:
        price: Bid price in IDR
        volume: Volume at this bid level (lots)
    """

    price: Decimal
    volume: int


@dataclass
class ScreenerCandidate:
    """A ticker that passed pre-open screening, with entry plan.

    Attributes:
        ticker: IDX ticker symbol
        iev: IEV value that triggered the screen
        entry_price: Suggested limit = prev_close * 1.005 (0.5% above yesterday's close)
        stop_loss_price: ATR-based stop (or legacy fixed-pct fallback)
        capital: Planned position size in IDR
        trend_signal: Signal from gap% + RSI gate (BULLISH/BEARISH/NEUTRAL)
        rsi: Latest RSI value if available
        sma: Latest SMA value if available (kept for backward compat, not used for trend)
        ai_summary: AI research summary (news, sentiment, affiliate tickers)
        atr: Latest ATR(14) value if available
        prev_close: Yesterday's closing price
        prev_high: Yesterday's high (intraday resistance reference)
        prev_low: Yesterday's low (intraday support reference)
        gap_pct: (pre_open_bid - prev_close) / prev_close * 100; None in fast mode
        entry_range_low: prev_close * (1 - max_gap_pct) — lower bound of safe open range
        entry_range_high: prev_close * (1 + max_gap_pct) — upper bound of safe open range
    """

    ticker: str
    iev: int
    entry_price: Decimal | None
    stop_loss_price: Decimal | None
    capital: Decimal
    trend_signal: str | None = None
    rsi: Decimal | None = None
    sma: Decimal | None = None
    ai_summary: str | None = None
    atr: Decimal | None = None
    prev_close: Decimal | None = None
    prev_high: Decimal | None = None
    prev_low: Decimal | None = None
    gap_pct: Decimal | None = None
    entry_range_low: Decimal | None = None
    entry_range_high: Decimal | None = None
    # Improvement #1 — smart money alignment
    accum_score: float | None = None       # 0–70 pts consistency + streak
    accum_tag: str | None = None           # BACKED / UNCONFIRMED / DISTRIBUTING
    accum_streak: int | None = None        # consecutive foreign buy days
    # Improvement #2 — foreign VWAP floor signal
    foreign_vwap: Decimal | None = None
    fvwap_discount_pct: float | None = None  # positive = foreigners underwater (bullish floor)

    @property
    def has_entry_plan(self) -> bool:
        return self.entry_price is not None

    @property
    def risk_reward_label(self) -> str:
        if not self.entry_price or not self.stop_loss_price:
            return "N/A"
        loss = self.entry_price - self.stop_loss_price
        pct = (loss / self.entry_price * 100).quantize(Decimal("0.1"))
        return f"-{pct}%"

    @property
    def entry_range_label(self) -> str:
        if self.entry_range_low and self.entry_range_high:
            return f"{self.entry_range_low:,.0f}–{self.entry_range_high:,.0f}"
        return "N/A"

    @property
    def gap_label(self) -> str:
        if self.gap_pct is None:
            return "—"
        sign = "+" if self.gap_pct >= 0 else ""
        return f"{sign}{float(self.gap_pct):.1f}%"


@dataclass
class PreOpenScreenResult:
    """Full result of a pre-open screening run.

    Attributes:
        screened_date: Date screening was run
        iev_min: IEV threshold used for filtering
        total_movers_seen: How many movers were evaluated before filtering
        candidates: Tickers that passed the screen, enriched with entry plan
    """

    screened_date: date
    iev_min: int
    total_movers_seen: int
    candidates: list[ScreenerCandidate]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)
