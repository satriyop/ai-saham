"""
JournalEntry — domain value object for paper trade log rows.

Written by `saham screen log`, enriched by `saham screen review`.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class JournalEntry:
    """One logged screening candidate with optional review data.

    Fields screened_at through rsi are written at log time.
    actual_* fields are filled in by review after market data is available.
    """

    screened_at: date
    ticker: str
    iev: int
    gap_pct: Decimal | None
    entry_range_low: Decimal | None
    entry_range_high: Decimal | None
    suggested_entry: Decimal | None
    atr_stop: Decimal | None
    trend: str | None
    rsi: Decimal | None
    # Filled by review
    actual_open: Decimal | None = None
    actual_close_1d: Decimal | None = None
    actual_close_5d: Decimal | None = None

    @property
    def in_range(self) -> bool | None:
        """True if actual_open fell inside the entry range."""
        if self.actual_open is None:
            return None
        if self.entry_range_low is None or self.entry_range_high is None:
            return None
        return self.entry_range_low <= self.actual_open <= self.entry_range_high

    @property
    def direction_1d(self) -> str | None:
        """UP/DOWN/FLAT based on 1-day close vs actual open."""
        if self.actual_open is None or self.actual_close_1d is None:
            return None
        if self.actual_close_1d > self.actual_open:
            return "UP"
        if self.actual_close_1d < self.actual_open:
            return "DOWN"
        return "FLAT"
