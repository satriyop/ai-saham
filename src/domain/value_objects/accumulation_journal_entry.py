"""
AccumulationJournalEntry — domain value object for accumulation trade log rows.

Written by `saham trade log swing`, enriched by `saham trade review swing`.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class AccumulationJournalEntry:
    """One logged accumulation candidate with optional review data.

    Fields logged_at through pattern are written at log time.
    actual_* fields are filled in by review after market data is available.
    """

    logged_at: date
    ticker: str
    entry_price: Decimal
    window_days: int
    accum_score: float | None
    foreign_flow_buy_streak: int | None
    flow_pct: Decimal | None
    vwap_disc_pct: Decimal | None
    bb_pctile: Decimal | None
    rsi: Decimal | None
    trend: str | None
    pattern: str | None
    setup: str | None = None
    setup_match: str | None = None
    failed_gates: tuple[str, ...] = ()
    regime: str | None = None
    planned_entry: Decimal | None = None
    planned_stop: Decimal | None = None
    planned_target: Decimal | None = None
    max_hold_days: int | None = None
    # Filled by review
    actual_close_5d: Decimal | None = None
    actual_close_10d: Decimal | None = None
    actual_close_20d: Decimal | None = None
    max_close_in_horizon: Decimal | None = None
    min_close_in_horizon: Decimal | None = None

    @property
    def return_10d_pct(self) -> float | None:
        """Percentage return from entry to 10-day close."""
        if self.actual_close_10d is None or self.entry_price == 0:
            return None
        return float((self.actual_close_10d - self.entry_price) / self.entry_price * 100)

    @property
    def is_winner_10d(self) -> bool | None:
        """True if 10-day close is above entry price."""
        r = self.return_10d_pct
        if r is None:
            return None
        return r > 0

    @property
    def max_upside_pct(self) -> float | None:
        """Max % gain achievable within horizon."""
        if self.max_close_in_horizon is None or self.entry_price == 0:
            return None
        return float((self.max_close_in_horizon - self.entry_price) / self.entry_price * 100)

    @property
    def max_drawdown_pct(self) -> float | None:
        """Max % loss within horizon."""
        if self.min_close_in_horizon is None or self.entry_price == 0:
            return None
        return float((self.min_close_in_horizon - self.entry_price) / self.entry_price * 100)
