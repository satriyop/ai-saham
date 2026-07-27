"""
BrokerDistributionSnapshot — cross-broker counterparty flow for one ticker/day.

Each entry in top_buyers / top_sellers names a broker and the counterparties on
the other side of their trades (the `distribute_to` list from the API).

Reading pattern:
  top_buyers[i].counterparties  → who YU BOUGHT FROM (they were the sellers)
  top_sellers[i].counterparties → who ZP SOLD TO (they were the buyers)

Signal interpretation:
  Foreign buyer ← domestic counterparties → retail distribution (smart money
  accumulating from local/retail).
  Foreign buyer ← foreign counterparties → institutional rotation.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class BrokerCounterparty:
    """One counterparty record inside a `distribute_to` list."""

    broker_code: str  # e.g. "ZP", "AK"
    broker_type: str  # e.g. "Asing", "Lokal", "Pemerintah"
    amount_idr: int  # IDR traded with this counterparty


@dataclass(frozen=True)
class BrokerDistributionEntry:
    """One top-buyer or top-seller broker with their counterparty breakdown."""

    broker_code: str
    broker_type: str
    amount_idr: int  # total buy or sell amount (IDR)
    counterparties: tuple[BrokerCounterparty, ...]  # sorted by amount desc

    @property
    def is_foreign(self) -> bool:
        return self.broker_type.lower() in ("asing",)

    @property
    def foreign_counterparty_pct(self) -> float:
        """Fraction of this broker's volume traded against other foreign brokers."""
        if not self.counterparties or self.amount_idr == 0:
            return 0.0
        foreign_amt = sum(
            c.amount_idr for c in self.counterparties if c.broker_type.lower() == "asing"
        )
        return foreign_amt / self.amount_idr * 100

    @property
    def domestic_counterparty_pct(self) -> float:
        """Fraction traded against domestic/retail brokers."""
        return 100.0 - self.foreign_counterparty_pct


@dataclass(frozen=True)
class BrokerDistributionSnapshot:
    """Cross-broker flow distribution for one ticker on one date.

    Attributes:
        ticker:      IDX ticker symbol
        date:        Trading date of the data
        top_buyers:  Brokers with highest buy value, each with counterparty breakdown
        top_sellers: Brokers with highest sell value, each with counterparty breakdown
        fetched_at:  When this record was retrieved from the API
    """

    ticker: str
    date: date
    top_buyers: tuple[BrokerDistributionEntry, ...]
    top_sellers: tuple[BrokerDistributionEntry, ...]
    fetched_at: datetime | None = None

    @property
    def net_foreign_buyer_dominance(self) -> bool:
        """True when top buyers are predominantly foreign (Asing) brokers."""
        if not self.top_buyers:
            return False
        foreign_count = sum(1 for b in self.top_buyers if b.is_foreign)
        return foreign_count / len(self.top_buyers) > 0.5

    @property
    def foreign_buying_from_domestic(self) -> bool:
        """True when the top foreign buyer has >50% domestic counterparties — accumulation
        signal."""
        foreign_buyers = [b for b in self.top_buyers if b.is_foreign]
        if not foreign_buyers:
            return False
        top = foreign_buyers[0]
        return top.domestic_counterparty_pct > 50.0
