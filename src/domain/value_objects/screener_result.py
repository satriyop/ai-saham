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
        entry_price: Suggested entry = best_bid + N ticks (None if order book unavailable)
        stop_loss_price: Hard stop = entry_price * (1 - stop_loss_pct)
        capital: Planned position size in IDR
        trend_signal: Signal from technical indicators (e.g., 'BULLISH', 'NEUTRAL', 'BEARISH')
        rsi: Latest RSI value if available
        sma: Latest SMA value if available
        ai_summary: AI research summary (news, sentiment, affiliate tickers)
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
