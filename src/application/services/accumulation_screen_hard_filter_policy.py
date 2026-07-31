"""Typed default screen hard-filter policy for live request and snapshot export.

Layer: Application (pure). No I/O.

Market-cap authority remains the live path:
``accumulation_screener.screener.min_market_cap_idr`` →
``SwingPolicyConfig.min_market_cap_idr`` → this object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AccumulationScreenHardFilterPolicy:
    """Immutable production defaults for the four challenged hard filters.

    Structural floors use ``enabled = floor > 0`` at payload time. Score filters
    store the configured enabled flags and floors. Capture neutralization must
    not mutate this object; neutralize only a derived request copy.
    """

    min_market_cap_idr: int
    min_piotroski: int
    min_accum_score: float
    min_accum_score_enabled: bool
    min_signal_score: float
    min_signal_score_enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.min_market_cap_idr, int):
            raise TypeError(
                f"min_market_cap_idr must be int, got {type(self.min_market_cap_idr).__name__}"
            )
        if not isinstance(self.min_piotroski, int):
            raise TypeError(f"min_piotroski must be int, got {type(self.min_piotroski).__name__}")
        if not isinstance(self.min_accum_score, float):
            raise TypeError(
                f"min_accum_score must be float, got {type(self.min_accum_score).__name__}"
            )
        if not isinstance(self.min_signal_score, float):
            raise TypeError(
                f"min_signal_score must be float, got {type(self.min_signal_score).__name__}"
            )
        if not isinstance(self.min_accum_score_enabled, bool):
            raise TypeError("min_accum_score_enabled must be bool")
        if not isinstance(self.min_signal_score_enabled, bool):
            raise TypeError("min_signal_score_enabled must be bool")

    @property
    def market_cap_enabled(self) -> bool:
        return self.min_market_cap_idr > 0

    @property
    def piotroski_enabled(self) -> bool:
        return self.min_piotroski > 0


def resolve_accumulation_screen_hard_filter_policy(
    *,
    swing_policy: Any,
    accumulation_screener_config: Any,
    min_accum_score: float | None = None,
    min_signal_score: float | None = None,
    min_piotroski: int = 0,
) -> AccumulationScreenHardFilterPolicy:
    """Resolve one hard-filter policy from typed configs + optional CLI overrides.

    Production snapshot / default baseline callers must pass no score overrides
    and default ``min_piotroski=0`` (canonical CLI/TUI default). CLI overrides
    force the corresponding score filter enabled when a score override is set.
    """
    foreign_filter = accumulation_screener_config.min_accum_score
    signal_filter = accumulation_screener_config.min_signal_score
    foreign_flow_enabled = bool(foreign_filter.enabled)
    signal_score_enabled = bool(signal_filter.enabled)
    if min_accum_score is None:
        accum_score = float(foreign_filter.value)
    else:
        accum_score = float(min_accum_score)
        foreign_flow_enabled = True
    if min_signal_score is None:
        signal_score = float(signal_filter.value)
    else:
        signal_score = float(min_signal_score)
        signal_score_enabled = True

    return AccumulationScreenHardFilterPolicy(
        min_market_cap_idr=int(swing_policy.min_market_cap_idr),
        min_piotroski=int(min_piotroski),
        min_accum_score=accum_score,
        min_accum_score_enabled=foreign_flow_enabled,
        min_signal_score=signal_score,
        min_signal_score_enabled=signal_score_enabled,
    )
