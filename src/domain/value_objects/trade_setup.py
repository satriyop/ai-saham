"""
TradeSetup — unified trade action verdict.

Aggregates SignalEngine and RiskEngine outputs into a single actionable
verdict per ticker. The authoritative answer to "should I act on this?"

SetupAction hierarchy (most severe first):
  BLOCKED_STRUCTURAL  — fundamental/liquidity/free_float gate failed; skip
  BLOCKED_EXECUTION   — bandar/execution gate failed; re-check in days
  AVOID               — signal weak; not worth attention
  WATCH               — signal moderate; monitor for improvement
  ENTER               — signal strong, all gates pass; conditions aligned

Layer: Domain
Depends on: stdlib, risk_signal, signal_assessment, market_context enums
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketRegime
    from src.domain.value_objects.signal_assessment import SignalStrength


class SetupAction(Enum):
    ENTER               = "ENTER"
    WATCH               = "WATCH"
    AVOID               = "AVOID"
    BLOCKED_EXECUTION   = "BLOCKED_EXECUTION"   # bandar distributing; re-check in days
    BLOCKED_STRUCTURAL  = "BLOCKED_STRUCTURAL"  # fundamental/liquidity/free_float; skip

    @property
    def is_blocked(self) -> bool:
        return self in (SetupAction.BLOCKED_STRUCTURAL, SetupAction.BLOCKED_EXECUTION)

    @property
    def is_actionable(self) -> bool:
        """True when conditions support taking a new entry (ENTER only)."""
        return self == SetupAction.ENTER

    @property
    def is_open_watchlist(self) -> bool:
        """True when the name belongs on pre-open track/confirm lists.

        ENTER = act; WATCH = monitor into the open. Distinct from
        ``is_actionable`` (ENTER only) so adapters do not invent parallel sets.
        """
        return self in (SetupAction.ENTER, SetupAction.WATCH)

    @property
    def display_sort_rank(self) -> int:
        """Lower rank first in discovery tables (ENTER → … → BLOCKED).

        Operator priority for screening, not severity order.
        """
        return _DISPLAY_SORT_RANK[self]

    @property
    def short(self) -> str:
        """Compact display label."""
        return _SHORT_LABELS[self]

    @classmethod
    def from_value(cls, value: "SetupAction | str | None") -> "SetupAction | None":
        """Parse enum member or string value; unknown → None."""
        if value is None:
            return None
        if isinstance(value, SetupAction):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            return None


_SHORT_LABELS: dict[SetupAction, str] = {
    SetupAction.ENTER:              "ENTER",
    SetupAction.WATCH:              "WATCH",
    SetupAction.AVOID:              "AVOID",
    SetupAction.BLOCKED_EXECUTION:  "BLOCKED(exec)",
    SetupAction.BLOCKED_STRUCTURAL: "BLOCKED(struct)",
}

# Discovery-table priority (not severity hierarchy in the class docstring)
_DISPLAY_SORT_RANK: dict[SetupAction, int] = {
    SetupAction.ENTER: 0,
    SetupAction.WATCH: 1,
    SetupAction.AVOID: 2,
    SetupAction.BLOCKED_EXECUTION: 3,
    SetupAction.BLOCKED_STRUCTURAL: 4,
}


@dataclass(frozen=True)
class TradeSetup:
    """
    Immutable unified verdict combining signal, risk, and regime assessments.

    Produced by AssessTradeSetupUseCase. Consumed by:
      - CLI display: one decisive action column per ticker
      - Learning loop: recorded to journal for grade/attribute/tune cycle
      - Screener: sortable, filterable action field

    signal_score_raw: pre-regime score (== signal_score when no MCE active).
    blocking_gates:   empty tuple when action is not BLOCKED_*.
    regime:           None when MarketContextEngine was not used.
    signal_multiplier: 1.0 when no regime adjustment; <1.0 = macro headwind.
    gate_tightening:  True when regime tightened gates (RISK_OFF / VOLATILE).
    """

    ticker: str
    snapshot_date: date
    action: SetupAction

    # Signal dimension
    signal_score: int                       # regime-adjusted 0–100
    signal_score_raw: int                   # pre-regime (== signal_score if no MCE)
    signal_strength: "SignalStrength"

    # Risk dimension — verdict is gate_triggered only; blocking_gates names the gate(s)
    blocking_gates: tuple[str, ...]         # empty when no gate blocked

    # Regime dimension (self-contained for learning loop)
    regime: "MarketRegime | None"
    signal_multiplier: float                # 1.0 = no impact; <1.0 = headwind
    gate_tightening: bool

    rationale: str

    def __post_init__(self) -> None:
        if not (0 <= self.signal_score <= 100):
            raise ValueError(f"signal_score must be 0–100, got {self.signal_score}")
        if not (0 <= self.signal_score_raw <= 100):
            raise ValueError(f"signal_score_raw must be 0–100, got {self.signal_score_raw}")
        if not (0.0 <= self.signal_multiplier <= 1.0):
            raise ValueError(f"signal_multiplier must be 0.0–1.0, got {self.signal_multiplier}")

    @property
    def regime_adjusted(self) -> bool:
        """True when the regime affected signal score or capped entry quality."""
        return self.signal_score < self.signal_score_raw or self.gate_tightening

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "action": self.action.value,
            "signal_score": self.signal_score,
            "signal_score_raw": self.signal_score_raw,
            "signal_strength": self.signal_strength.value,
            "gate_triggered": self.blocking_gates[0] if self.blocking_gates else None,
            "blocking_gates": list(self.blocking_gates),
            "regime": self.regime.value if self.regime else None,
            "signal_multiplier": self.signal_multiplier,
            "gate_tightening": self.gate_tightening,
            "rationale": self.rationale,
        }
