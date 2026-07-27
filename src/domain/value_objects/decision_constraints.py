"""
Decision constraint value objects.

DecisionConstraints is emitted by SignalEngine policy resolution so downstream
workflow code can see why an otherwise strong signal is capped by regime/setup
policy. It does not compute stop, target, or position size.

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionConstraints:
    max_decision: str
    regime: str | None
    regime_enter_allowed: bool
    regime_size_multiplier: float
    setup_family: str | None
    setup_regime_action: str | None
    effective_size_multiplier: float
    constraint_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (0.0 <= self.regime_size_multiplier <= 1.0):
            raise ValueError(
                f"regime_size_multiplier must be 0.0-1.0, got {self.regime_size_multiplier}"
            )
        if not (0.0 <= self.effective_size_multiplier <= 1.0):
            raise ValueError(
                f"effective_size_multiplier must be 0.0-1.0, got {self.effective_size_multiplier}"
            )

    def to_dict(self) -> dict:
        return {
            "max_decision": self.max_decision,
            "regime": self.regime,
            "regime_enter_allowed": self.regime_enter_allowed,
            "regime_size_multiplier": self.regime_size_multiplier,
            "setup_family": self.setup_family,
            "setup_regime_action": self.setup_regime_action,
            "effective_size_multiplier": self.effective_size_multiplier,
            "constraint_reasons": list(self.constraint_reasons),
        }
