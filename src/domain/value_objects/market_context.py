"""
Market Context value objects.

Output contract for the MarketContextEngine: the authoritative cross-market
regime assessment consumed by SignalEngine (signal_multiplier) and RiskEngine
(gate_tightening) as the macro environment overlay.

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class MarketRegime(Enum):
    RISK_ON  = "RISK_ON"
    NEUTRAL  = "NEUTRAL"
    RISK_OFF = "RISK_OFF"
    VOLATILE = "VOLATILE"   # hard override when VIX > volatile_threshold


@dataclass(frozen=True)
class ContextFactor:
    """
    Single evaluated factor contributing to the market regime.

    score=None means the factor was skipped (disabled or data unavailable).
    weight is the pre-renormalization config weight.
    """

    name: str            # "vix" | "eido" | "usd_idr" | "idx_trend" | "idx_breadth"
    enabled: bool
    value: float | None  # raw measurement (e.g. VIX = 28.4); None = no data
    score: float | None  # 0.0 (bearish) → 1.0 (bullish); None = skipped
    weight: float        # config weight before renormalization
    label: str           # "FAVORABLE" | "NEUTRAL" | "STRESSED" | "UNAVAILABLE" | "DISABLED"
    rationale: str       # human-readable explanation (e.g. "VIX 28.4 above risk_off 25.0")


@dataclass(frozen=True)
class MarketContext:
    """
    Immutable result of market regime evaluation.

    Produced by BuildMarketContextUseCase and consumed by:
      - SignalEngine:  score × signal_multiplier → adjusted signal score
      - RiskEngine:    gate_tightening=True → use stricter gate thresholds
      - CLI:           display regime + factor breakdown

    conviction is the renormalized weighted composite score (0.0–1.0).
    regime_thresholds in config control how conviction maps to MarketRegime.
    """

    regime: MarketRegime
    conviction: float                       # weighted composite 0.0–1.0
    factors: tuple[ContextFactor, ...]
    signal_multiplier: float                # applied to SignalAssessment.score
    gate_tightening: bool                   # True → RiskEngine tightens gate thresholds
    as_of_date: date
    staleness_warning: str | None = None    # when any factor data is T-1 or older
    coverage_warning: str | None = None     # when ≥ half enabled factors are unavailable

    # ── A2: regime quality metadata (None until RegimeDetectionEvidence is built) ──
    regime_confidence: float | None = None   # 0.0–1.0; distance from nearest regime boundary
    regime_stability: str | None = None      # "STABLE" | "TRANSITIONING" | "UNKNOWN"
    days_in_regime: int | None = None        # consecutive days in current regime
    transition_warning: str | None = None    # human-readable when TRANSITIONING

    def __post_init__(self) -> None:
        if not (0.0 <= self.conviction <= 1.0):
            raise ValueError(f"conviction must be 0.0–1.0, got {self.conviction}")
        if not (0.0 <= self.signal_multiplier <= 1.0):
            raise ValueError(f"signal_multiplier must be 0.0–1.0, got {self.signal_multiplier}")
        if self.regime_confidence is not None and not (0.0 <= self.regime_confidence <= 1.0):
            raise ValueError(f"regime_confidence must be 0.0–1.0, got {self.regime_confidence}")

    @property
    def regime_label(self) -> str:
        return self.regime.value

    @property
    def available_factors(self) -> list[ContextFactor]:
        return [f for f in self.factors if f.score is not None]

    @property
    def unavailable_factors(self) -> list[ContextFactor]:
        return [f for f in self.factors if f.enabled and f.score is None]

    def factor(self, name: str) -> ContextFactor | None:
        return next((f for f in self.factors if f.name == name), None)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "conviction": round(self.conviction, 4),
            "signal_multiplier": self.signal_multiplier,
            "gate_tightening": self.gate_tightening,
            "as_of_date": self.as_of_date.isoformat(),
            "staleness_warning": self.staleness_warning,
            "coverage_warning": self.coverage_warning,
            "regime_confidence": round(self.regime_confidence, 4) if self.regime_confidence is not None else None,
            "regime_stability": self.regime_stability,
            "days_in_regime": self.days_in_regime,
            "transition_warning": self.transition_warning,
            "factors": [
                {
                    "name": f.name,
                    "enabled": f.enabled,
                    "value": round(f.value, 4) if f.value is not None else None,
                    "score": round(f.score, 4) if f.score is not None else None,
                    "weight": f.weight,
                    "label": f.label,
                    "rationale": f.rationale,
                }
                for f in self.factors
            ],
        }
