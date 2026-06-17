"""
AnalystConsensus value object.

Holds aggregated analyst buy/hold/sell ratings and price target for a ticker.
Sourced from Stockbit /analyst-ratings/{ticker} endpoint.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AnalystConsensus:
    ticker: str
    buy_count: int
    hold_count: int
    sell_count: int
    avg_price_target: float | None    # IDR; Stockbit's "best_target"
    current_price: float | None       # IDR at time of last update
    last_updated: date | None

    @property
    def analyst_count(self) -> int:
        return self.buy_count + self.hold_count + self.sell_count

    @property
    def upside_pct(self) -> float | None:
        if self.avg_price_target and self.current_price and self.current_price > 0:
            return (self.avg_price_target - self.current_price) / self.current_price * 100
        return None

    @property
    def is_bullish(self) -> bool:
        return self.buy_count > (self.hold_count + self.sell_count)

    @property
    def consensus_label(self) -> str:
        if self.analyst_count == 0:
            return "N/A"
        if self.sell_count > self.hold_count and self.sell_count >= self.buy_count:
            return "SELL"
        if self.buy_count > (self.hold_count + self.sell_count):
            return "BUY"
        if self.hold_count >= self.buy_count and self.hold_count >= self.sell_count:
            return "HOLD"
        return "MIXED"

    @property
    def label(self) -> str:
        parts = []
        if self.buy_count:
            parts.append(f"{self.buy_count}B")
        if self.hold_count:
            parts.append(f"{self.hold_count}H")
        if self.sell_count:
            parts.append(f"{self.sell_count}S")
        rating = " ".join(parts) if parts else "0"
        if self.avg_price_target and self.upside_pct is not None:
            target_k = int(self.avg_price_target)
            return f"{rating} | target Rp{target_k:,} ({self.upside_pct:+.1f}%)"
        return rating

    def to_dict(self) -> dict:
        return {
            "buy_count": self.buy_count,
            "hold_count": self.hold_count,
            "sell_count": self.sell_count,
            "analyst_count": self.analyst_count,
            "consensus_label": self.consensus_label,
            "avg_price_target": self.avg_price_target,
            "upside_pct": round(self.upside_pct, 1) if self.upside_pct is not None else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }
