"""RiskGate — domain abstraction for structural and execution risk filters.

Gates are pure functions: they receive pre-loaded data via GateContext and
return a GateResult. No IO, no database access. GateContext is populated by
the application layer (AssessRiskUseCase / RiskEngine) before gate evaluation.

The verdict is purely `gate_triggered`: a gate either fires (triggered=True)
or it does not. Gates no longer override an intermediate RiskLevel.

Orthogonal to that verdict, `GateResult.outcome` records *what the gate was able
to determine*: it reached a clean verdict (PASS / TRIGGERED) or it had no usable
input at all (UNEVALUABLE). An unevaluable gate is never a silent pass — whether
it blocks is a separate, policy-driven decision carried by `triggered`.

Layer: Domain
Depends on: Domain value objects only
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


class GateOutcome(str, Enum):
    """What a gate was able to determine — independent of whether it blocks.

    ``UNEVALUABLE`` means the gate had no usable input and therefore asserts
    nothing about the ticker. It is deliberately *not* a flavour of ``PASS``:
    "checked and clean" and "never checked" must stay discriminable at the type
    level, not only through the free-text ``reason``.
    """

    PASS = "pass"
    TRIGGERED = "triggered"
    UNEVALUABLE = "unevaluable"


@dataclass(frozen=True)
class GateResult:
    """Outcome from a single RiskGate evaluation.

    ``outcome`` is derived from ``triggered`` unless stated explicitly, so a
    gate can only produce ``UNEVALUABLE`` on purpose — via
    :meth:`GateResult.unevaluable`. ``outcome`` is never ``None`` after
    construction.
    """

    triggered: bool
    reason: str  # human-readable; surfaced in RiskAssessment rationale
    confidence: int = 100  # confidence of the trigger (0, 50, 80, or 100)
    outcome: GateOutcome | None = None

    def __post_init__(self) -> None:
        if self.outcome is None:
            object.__setattr__(
                self,
                "outcome",
                GateOutcome.TRIGGERED if self.triggered else GateOutcome.PASS,
            )
            return
        if self.outcome is GateOutcome.TRIGGERED and not self.triggered:
            raise ValueError("GateOutcome.TRIGGERED requires triggered=True")
        if self.outcome is GateOutcome.PASS and self.triggered:
            raise ValueError("GateOutcome.PASS requires triggered=False")

    @classmethod
    def unevaluable(
        cls,
        *,
        reason: str,
        confidence: int = 0,
        blocks: bool = False,
    ) -> GateResult:
        """Build the "no usable input" result.

        ``blocks`` is the gate's configured missing-data action, not a verdict
        about the ticker: the gate still asserts nothing either way.
        """
        return cls(
            triggered=blocks,
            reason=reason,
            confidence=confidence,
            outcome=GateOutcome.UNEVALUABLE,
        )

    @property
    def is_unevaluable(self) -> bool:
        """True when the gate had no usable input for this context."""
        return self.outcome is GateOutcome.UNEVALUABLE


@dataclass(frozen=True)
class GateContext:
    """
    Pre-loaded data snapshot passed to all gates.

    The application layer is responsible for populating this before gate
    evaluation. Gates receive only plain Python values — no repositories,
    no IO, no lazy loading.
    """

    ticker: str
    snapshot_date: date

    # Structural: sourced from CompanyFundamentals (quarterly refresh)
    piotroski_f_score: int | None = None
    market_cap_idr: int | None = None

    # Structural: sourced from ShareholdingComposition (quarterly refresh)
    free_float_pct: float | None = None

    # Execution: sourced from BandarDetectorSnapshot (daily)
    five_day_accdist: str | None = None

    # Liquidity: filled by AssessRiskUseCase from MarketDataRepository
    recent_candles: tuple = field(default_factory=tuple)  # tuple[Candle, ...]

    # Technical: latest indicator snapshot, for TechnicalGate (optional gate)
    latest_snapshot: "IndicatorSnapshot | None" = None


class RiskGate(ABC):
    """Abstract gate that fires (or not) against a GateContext.

    Structural gates (FundamentalGate, LiquidityGate, FreeFloatGate) run first
    and short-circuit to BLOCKED_STRUCTURAL. Execution gates (BandarGate,
    TechnicalGate) run after and short-circuit to BLOCKED_EXECUTION.
    """

    @abstractmethod
    def evaluate(self, context: GateContext) -> GateResult:
        """Evaluate the gate against the provided context."""
