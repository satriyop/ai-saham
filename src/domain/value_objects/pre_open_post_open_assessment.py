"""
Value objects for pre-open strategy post-open assessment.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class PreOpenPostOpenDecision(str, Enum):
    """Deterministic post-open decision labels."""

    ENTER = "ENTER"
    WAIT = "WAIT"
    SKIP_GAP_UP = "SKIP_GAP_UP"
    SKIP_GAP_DOWN = "SKIP_GAP_DOWN"
    SKIP_BEARISH_CONTEXT = "SKIP_BEARISH_CONTEXT"
    SKIP_RISK_TOO_WIDE = "SKIP_RISK_TOO_WIDE"
    SKIP_INSUFFICIENT_DATA = "SKIP_INSUFFICIENT_DATA"
    SKIP_LOW_VOLATILITY = "SKIP_LOW_VOLATILITY"


@dataclass(frozen=True)
class PreOpenPostOpenCandidate:
    """Pre-open candidate plus actual opening price for confirmation."""

    ticker: str
    opening_price: Decimal | None
    iev: int | None = None
    entry_range_low: Decimal | None = None
    entry_range_high: Decimal | None = None
    suggested_entry: Decimal | None = None
    atr_stop: Decimal | None = None
    trend: str | None = None
    rsi: Decimal | None = None
    gap_pct: Decimal | None = None
    opening_broker_backing_tag: str | None = None
    fvwap_discount_pct: Decimal | None = None
    opening_price_source: str | None = None
    opening_price_confidence: str | None = None
    opening_price_timestamp: str | None = None
    auto_confirmed: bool = False
    manual_override: bool = False


@dataclass(frozen=True)
class PreOpenPostOpenAssessment:
    """Final confirmation result for one ticker."""

    ticker: str
    decision: PreOpenPostOpenDecision
    opening_price: Decimal | None
    planned_entry: Decimal | None
    stop_loss_price: Decimal | None
    stop_pct: Decimal | None
    reasons: tuple[str, ...]
    iev: int | None = None
    trend: str | None = None
    rsi: Decimal | None = None
    gap_pct: Decimal | None = None
    opening_broker_backing_tag: str | None = None
    fvwap_discount_pct: Decimal | None = None
    opening_price_source: str | None = None
    opening_price_confidence: str | None = None
    opening_price_timestamp: str | None = None
    auto_confirmed: bool = False
    manual_override: bool = False


@dataclass(frozen=True)
class PreOpenPostOpenResult:
    """Full result of a post-open confirmation run."""

    confirmed_date: date
    max_stop_pct: Decimal
    confirmations: tuple[PreOpenPostOpenAssessment, ...]


@dataclass(frozen=True)
class PreOpenPaperJournalEntry:
    """One logged post-open confirmation row."""

    confirmed_at: date
    ticker: str
    decision: str
    reason_codes: tuple[str, ...]
    opening_price: Decimal | None
    planned_entry: Decimal | None
    stop_loss_price: Decimal | None
    stop_pct: Decimal | None
    iev: int | None = None
    trend: str | None = None
    rsi: Decimal | None = None
    gap_pct: Decimal | None = None
    opening_broker_backing_tag: str | None = None
    fvwap_discount_pct: Decimal | None = None
    actual_entry_price: Decimal | None = None
    actual_exit_price: Decimal | None = None
    outcome_result: str | None = None
    outcome_r: Decimal | None = None
    outcome_notes: str | None = None

    @property
    def gap_bucket(self) -> str:
        if self.gap_pct is None:
            return "gap:missing"
        value = abs(self.gap_pct)
        if value <= Decimal("1"):
            return "gap:0-1"
        if value <= Decimal("3"):
            return "gap:1-3"
        return "gap:>3"

    @property
    def rsi_bucket(self) -> str:
        if self.rsi is None:
            return "rsi:missing"
        if self.rsi < Decimal("30"):
            return "rsi:<30"
        if self.rsi <= Decimal("55"):
            return "rsi:30-55"
        if self.rsi <= Decimal("70"):
            return "rsi:55-70"
        return "rsi:>70"

    @property
    def stop_bucket(self) -> str:
        if self.stop_pct is None:
            return "stop:missing"
        if self.stop_pct <= Decimal("2"):
            return "stop:0-2"
        if self.stop_pct <= Decimal("5"):
            return "stop:2-5"
        return "stop:>5"

    @property
    def fvwap_bucket(self) -> str:
        if self.fvwap_discount_pct is None:
            return "fvwap:missing"
        if self.fvwap_discount_pct > 0:
            return "fvwap:positive"
        return "fvwap:nonpositive"

    @property
    def has_manual_outcome(self) -> bool:
        return self.actual_entry_price is not None and self.actual_exit_price is not None
