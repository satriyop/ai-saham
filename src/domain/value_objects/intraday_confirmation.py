"""
Value objects for intraday post-open confirmation.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class IntradayDecision(str, Enum):
    """Deterministic post-open decision labels."""

    ENTER = "ENTER"
    WAIT = "WAIT"
    SKIP_GAP_UP = "SKIP_GAP_UP"
    SKIP_GAP_DOWN = "SKIP_GAP_DOWN"
    SKIP_BEARISH_CONTEXT = "SKIP_BEARISH_CONTEXT"
    SKIP_RISK_TOO_WIDE = "SKIP_RISK_TOO_WIDE"
    SKIP_INSUFFICIENT_DATA = "SKIP_INSUFFICIENT_DATA"


@dataclass(frozen=True)
class IntradayConfirmationCandidate:
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
    accum_tag: str | None = None
    fvwap_discount_pct: Decimal | None = None


@dataclass(frozen=True)
class IntradayConfirmation:
    """Final confirmation result for one ticker."""

    ticker: str
    decision: IntradayDecision
    opening_price: Decimal | None
    planned_entry: Decimal | None
    stop_loss_price: Decimal | None
    stop_pct: Decimal | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class IntradayConfirmationResult:
    """Full result of a post-open confirmation run."""

    confirmed_date: date
    max_stop_pct: Decimal
    confirmations: tuple[IntradayConfirmation, ...]
