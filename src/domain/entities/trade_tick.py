"""
TradeTick — immutable entity representing a single executed trade from the running trade feed.

Fields map directly to the Stockbit /order-trade/running-trade endpoint response.
investor_type classifies the buyer/seller pair as Foreign, Domestic, or Mixed.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TradeTick:
    """One executed trade tick from the Stockbit running-trade feed.

    Attributes:
        ticker:             IDX ticker symbol
        timestamp:          Execution time of this tick
        price:              Trade price (IDR)
        lot:                Volume in lots (1 lot = 100 shares)
        buyer_broker_code:  Broker code of the buyer side (e.g. "AK", "YP")
        seller_broker_code: Broker code of the seller side
        trade_type:         "T" (trade), "AT" (auto-match), etc. from feed
        investor_type:      Stockbit investor classification — "F" foreign, "D" domestic, "X" mixed
    """

    ticker: str
    timestamp: datetime
    price: float
    lot: int
    buyer_broker_code: str
    seller_broker_code: str
    trade_type: str = ""
    investor_type: str = ""

    @property
    def value(self) -> float:
        """Trade value in IDR (price × lot × 100 shares/lot)."""
        return self.price * self.lot * 100

    @property
    def is_foreign_buyer(self) -> bool:
        return self.investor_type.upper() == "F"
