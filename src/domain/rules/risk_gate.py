"""
RiskGate — domain abstraction for structural and execution risk filters.

Gates augment or override the technical rule engine's assessment with
non-technical data (fundamentals, liquidity, institutional flow).

All gates are pure functions: they receive pre-loaded data via GateContext
and return a GateResult. No IO, no database access.

GateContext is populated by the application layer (AssessRiskUseCase)
before gate evaluation. Each gate extracts only what it needs.

Layer: Domain
Depends on: Domain value objects only
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from src.domain.value_objects.risk_signal import RiskLevel

if TYPE_CHECKING:
    from src.domain.entities.candle import Candle


@dataclass(frozen=True)
class GateResult:
    """Outcome from a single RiskGate evaluation."""

    triggered: bool
    override_risk: RiskLevel | None  # set when triggered; replaces current assessment
    reason: str                       # human-readable; included in RiskAssessment rationale
    confidence: int = 100             # confidence of the override (0, 50, or 100)


@dataclass(frozen=True)
class GateContext:
    """
    Pre-loaded data snapshot passed to all gates.

    The application layer is responsible for populating this before gate
    evaluation. Gates receive only plain Python values — no repositories,
    no IO, no lazy loading.

    Structural data (piotroski, market_cap) is quarterly; execution data
    (bandar) is daily. The caller should populate only the fields relevant
    to the gates it is running.
    """

    ticker: str
    snapshot_date: date

    # Structural: sourced from CompanyFundamentals (quarterly refresh)
    piotroski_f_score: int | None = None
    market_cap_idr: int | None = None

    # Structural: sourced from ShareholdingComposition (quarterly refresh)
    # Computed as individual_pct + institution_pct from IDX disclosure.
    # Upper-bound proxy: institution_pct may include some strategic holders.
    free_float_pct: float | None = None

    # Execution: sourced from BandarDetectorSnapshot (daily)
    five_day_accdist: str | None = None   # "Big Acc" | "Small Acc" | "Neutral" | "Small Dist" | "Big Dist"
    bandar_is_distributing: bool = False  # True when five_day score < 0

    # Liquidity: filled by AssessRiskUseCase from MarketDataRepository
    recent_candles: tuple = field(default_factory=tuple)  # tuple[Candle, ...]


class RiskGate(ABC):
    """Abstract gate that can override or augment a risk assessment.

    Structural gates (FundamentalGate, LiquidityGate) run before the rule
    engine and can short-circuit to HIGH_RISK.

    Execution gates (BandarGate) run after the rule engine and can downgrade
    a LOW_RISK technical result when conflicting signals exist.
    """

    @abstractmethod
    def evaluate(self, context: GateContext, current_risk: RiskLevel) -> GateResult:
        """
        Evaluate the gate against the provided context.

        Args:
            context: Pre-loaded data for gate evaluation.
            current_risk: Risk level to test against. Structural gates ignore
                         this; execution gates use it for conditional downgrades.

        Returns:
            GateResult with triggered=True and override_risk set if the gate fires.
        """
