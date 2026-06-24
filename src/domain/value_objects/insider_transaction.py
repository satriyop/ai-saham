"""
InsiderTransaction — immutable value object for one insider buy/sell filing.

Sourced from IDX disclosures via Stockbit /insider/company/majorholder.
Represents a director, commissioner, or major shareholder transaction.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class InsiderTransaction:
    """One insider ownership change as filed with IDX.

    Attributes:
        ticker:               IDX ticker symbol
        name:                 Insider's full name
        role:                 "DIREKTUR", "KOMISARIS", "MAJOR_HOLDER", or ""
        action_type:          "BUY" or "SELL"
        shares:               Number of shares transacted (always positive)
        price:                Price per share at transaction date (IDR; 0 if not disclosed)
        transaction_date:     Filing/transaction date
        ownership_before_pct: Ownership % before this transaction
        ownership_after_pct:  Ownership % after this transaction
    """

    ticker: str
    name: str
    role: str
    action_type: str          # "BUY" | "SELL"
    shares: int
    price: float              # IDR per share; 0 if undisclosed
    transaction_date: date
    ownership_before_pct: float
    ownership_after_pct: float

    @property
    def is_buy(self) -> bool:
        return self.action_type == "BUY"

    @property
    def is_director_or_commissioner(self) -> bool:
        return self.role in ("DIREKTUR", "KOMISARIS")

    @property
    def label(self) -> str:
        """Short human-readable summary, e.g. 'SANTOSO (Dir) bought 495K @ Rp6,982'."""
        action = "bought" if self.is_buy else "sold"
        shares_str = f"{self.shares:,}"
        price_str = f" @ Rp{self.price:,.0f}" if self.price > 0 else ""
        role_str = f" ({self.role[:3].title()})" if self.role else ""
        return f"{self.name}{role_str} {action} {shares_str}{price_str}"


def compute_net_buy_ratio(transactions: list["InsiderTransaction"]) -> float | None:
    """Return share-weighted net buy ratio in [-1.0, +1.0].

    +1.0 = all insider volume is buying; -1.0 = all volume is selling.
    Returns None when there are no transactions (degrades to neutral 50.0 in scoring).
    """
    buy_shares = sum(t.shares for t in transactions if t.is_buy)
    sell_shares = sum(t.shares for t in transactions if not t.is_buy)
    total = buy_shares + sell_shares
    if total == 0:
        return None
    return (buy_shares - sell_shares) / total
