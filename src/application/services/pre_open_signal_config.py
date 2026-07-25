"""Config for pre-open v1 signal cascade (ADR-048).

Weights are provisional and only used if a future composite path is enabled.
v1 champion is ordinal cascade; production must not dual-path cascade+composite.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PreOpenSignalConfig:
    """Deterministic, config-driven pre-open signal policy."""

    # Rendering: cascade (v1 champion) XOR composite (v2 provisional)
    rendering: str = "cascade"  # "cascade" | "composite"

    # Auction floor: below → no production signal
    auction_min: int = 50

    # Strength bands on auction-derived score (0–100)
    strong_min: int = 70
    moderate_min: int = 50

    # Gap_out if abs(gap_pct) > gap_out_abs_pct (percentage points)
    gap_out_abs_pct: Decimal = Decimal("5")

    # Friction: spread wider than this % fails viability (when spread known)
    max_spread_pct: Decimal = Decimal("1.5")

    # RSI extension veto threshold
    rsi_extension_threshold: Decimal = Decimal("75")

    # Provisional composite weights (only if rendering=composite)
    auction_weight: float = 0.65
    viability_weight: float = 0.35

    def __post_init__(self) -> None:
        if self.rendering not in ("cascade", "composite"):
            raise ValueError(
                f"rendering must be 'cascade' or 'composite', got {self.rendering!r}"
            )
        if not (0 <= self.auction_min <= 100):
            raise ValueError(f"auction_min must be 0–100, got {self.auction_min}")
        if not (0.0 < self.auction_weight < 1.0):
            raise ValueError("auction_weight must be in (0, 1)")
        if abs(self.auction_weight + self.viability_weight - 1.0) > 1e-9:
            raise ValueError("auction_weight + viability_weight must equal 1.0")
