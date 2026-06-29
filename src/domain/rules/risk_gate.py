"""RiskGate — domain abstraction for structural and execution risk filters.

Gates are pure functions: they receive pre-loaded data via GateContext and
return a GateResult. No IO, no database access. GateContext is populated by
the application layer (AssessRiskUseCase / RiskEngine) before gate evaluation.

The verdict is purely `gate_triggered`: a gate either fires (triggered=True)
or it does not. Gates no longer override an intermediate RiskLevel.

Layer: Domain
Depends on: Domain value objects only
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


@dataclass(frozen=True)
class GateResult:
    """Outcome from a single RiskGate evaluation."""

    triggered: bool
    reason: str                       # human-readable; surfaced in RiskAssessment rationale
    confidence: int = 100             # confidence of the trigger (0, 50, 80, or 100)


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
