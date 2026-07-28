"""
RunningTradeSignal — immutable summary of institutional broker activity in recent ticks.

Produced by running_trade_analysis use case from a list of TradeTick objects.
Used as a supplementary intraday confirmation signal during the opening session.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class RunningTradeSignal:
    """Aggregated institutional broker activity from running-trade ticks.

    Attributes:
        ticker:                   IDX ticker symbol
        as_of:                    Timestamp of the most recent tick analysed
        tick_count:               Total ticks processed
        institutional_net_lot:    Net lot position of institutional brokers (buy − sell)
        institutional_net_value:  Net value in IDR (buy_value − sell_value)
        absorption_ratio:         institutional_buy_lot / total_buy_lot (0–1)
        dominant_side:            "BUY" when institutions net buy, "SELL" when net sell, "NEUTRAL"
    """

    ticker: str
    as_of: datetime
    tick_count: int
    institutional_net_lot: int
    institutional_net_value: float
    absorption_ratio: float  # 0–1: fraction of buy-side held by institutions
    dominant_side: Literal["BUY", "SELL", "NEUTRAL"]

    @property
    def is_absorbing(self) -> bool:
        """True when institutions are net buyers and absorbing ≥50% of buy-side flow."""
        return self.dominant_side == "BUY" and self.absorption_ratio >= 0.5

    @property
    def label(self) -> str:
        """Human-readable summary, e.g. 'BUY (abs 72%, net +340L)'."""
        return (
            f"{self.dominant_side}"
            f" (abs {self.absorption_ratio * 100:.0f}%,"
            f" net {self.institutional_net_lot:+d}L)"
        )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "as_of": self.as_of.isoformat(),
            "tick_count": self.tick_count,
            "institutional_net_lot": self.institutional_net_lot,
            "institutional_net_value": round(self.institutional_net_value, 0),
            "absorption_ratio": round(self.absorption_ratio, 4),
            "dominant_side": self.dominant_side,
            "is_absorbing": self.is_absorbing,
            "label": self.label,
        }
