"""
TradeJournalStore port — abstract persistence for unified trade journal.

Records are plain dicts with a "trade_type" discriminator.
Forward tokens: "accum" | "pre-open".
Legacy raw rows may still use "swing" | "intraday" (not rewritten).

Dedup key:
  accum/swing → (trade_type, logged_at, ticker, window_days)
  pre-open/other → (trade_type, logged_at, ticker)

Layer: Domain
"""

from abc import ABC, abstractmethod


class TradeJournalStore(ABC):
    @abstractmethod
    def append(self, record: dict) -> bool:
        """Append record. Idempotent by dedup key. Returns True if written, False if duplicate."""

    @abstractmethod
    def read_all(self) -> list[dict]:
        """Return all records sorted by (logged_at, ticker)."""

    @abstractmethod
    def update(self, record: dict) -> bool:
        """Overwrite matching record in-place. Returns True if found."""
