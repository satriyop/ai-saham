"""
RegimeDetectionEvidence — immutable fingerprint of market-regime detection inputs.

This value object is the persistence/audit record produced alongside MarketContext.
It stores ALL raw detection input values so regime observations can be replayed
deterministically without network access and validated against market-level forward
labels.

It does NOT score tickers, mutate signals, or change decision precedence.
Forward label slots (forward_ihsg_return_*) start as None and are filled
retroactively when future IHSG candles are available.

IDX foreign-flow inputs (idx_foreign_flow_*, streaks) are DIAGNOSTIC only —
they go in the fingerprint but have no scoring weight.

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class RegimeStability(Enum):
    STABLE = "STABLE"
    TRANSITIONING = "TRANSITIONING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeDetectionEvidence:
    """
    Full fingerprint of one market-regime observation.

    Produced by MarketContextEngine.evaluate() and persisted to regime_observations.
    schema_version = 1 for all A2 observations.
    """

    observation_date: date
    schema_version: int  # always 1 for A2

    # ── Regime output ──────────────────────────────────────────────────────────
    regime: str  # MarketRegime.value
    regime_score: float  # conviction from BuildMarketContextUseCase (0.0–1.0)
    regime_confidence: float  # how confidently the label was detected (0.0–1.0)
    regime_stability: RegimeStability
    days_in_regime: int | None  # None when no prior observations exist
    transition_warning: str | None  # human-readable when TRANSITIONING

    # ── IHSG detection inputs ─────────────────────────────────────────────────
    ihsg_20d_return: float | None  # IHSG close return over 20 trading days
    ihsg_trend_structure: str | None  # "ABOVE_BOTH"|"ABOVE_FAST_ONLY"|"BELOW_BOTH"|"UNKNOWN"
    ihsg_breadth_pct_above_ma: float | None  # % of universe above SMA20 (from idx_breadth factor)
    ihsg_volume_trend: float | None  # recent 5d avg vol / 20d avg vol ratio
    ihsg_atr_pct: float | None  # 14d ATR / close × 100

    # ── IDX foreign-flow inputs (DIAGNOSTIC only — no scoring weight) ─────────
    idx_foreign_flow_5d: float | None  # sum of net foreign value, last 5 days (IDR)
    idx_foreign_flow_20d: float | None  # sum of net foreign value, last 20 days (IDR)
    foreign_buy_streak: int | None  # consecutive tail days with net_value > 0
    foreign_sell_streak: int | None  # consecutive tail days with net_value < 0

    # ── Sector inputs (UNAVAILABLE in A2 unless banking universe configured) ──
    banking_sector_vs_ihsg: float | None  # banking equal-weight return vs IHSG 20d
    sector_breadth: float | None  # proxy: same as ihsg_breadth_pct_above_ma for now

    # ── Forward labels (filled retroactively; None until future candles exist) ─
    forward_ihsg_return_5d: float | None = None
    forward_ihsg_return_10d: float | None = None
    forward_ihsg_return_20d: float | None = None

    # ── Config cohort identity (legacy rows use empty strings) ─────────────────
    semantic_compatibility_id: str = ""
    observation_contract: str = ""
    universe_name: str = ""
    benchmark_ticker: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.regime_score <= 1.0):
            raise ValueError(f"regime_score must be 0.0–1.0, got {self.regime_score}")
        if not (0.0 <= self.regime_confidence <= 1.0):
            raise ValueError(f"regime_confidence must be 0.0–1.0, got {self.regime_confidence}")

    def to_dict(self) -> dict:
        return {
            "observation_date": self.observation_date.isoformat(),
            "schema_version": self.schema_version,
            "regime": self.regime,
            "regime_score": round(self.regime_score, 4),
            "regime_confidence": round(self.regime_confidence, 4),
            "regime_stability": self.regime_stability.value,
            "days_in_regime": self.days_in_regime,
            "transition_warning": self.transition_warning,
            "ihsg_20d_return": (
                round(self.ihsg_20d_return, 4) if self.ihsg_20d_return is not None else None
            ),
            "ihsg_trend_structure": self.ihsg_trend_structure,
            "ihsg_breadth_pct_above_ma": (
                round(self.ihsg_breadth_pct_above_ma, 4)
                if self.ihsg_breadth_pct_above_ma is not None
                else None
            ),
            "ihsg_volume_trend": (
                round(self.ihsg_volume_trend, 4) if self.ihsg_volume_trend is not None else None
            ),
            "ihsg_atr_pct": round(self.ihsg_atr_pct, 4) if self.ihsg_atr_pct is not None else None,
            "idx_foreign_flow_5d": (
                round(self.idx_foreign_flow_5d, 2) if self.idx_foreign_flow_5d is not None else None
            ),
            "idx_foreign_flow_20d": (
                round(self.idx_foreign_flow_20d, 2)
                if self.idx_foreign_flow_20d is not None
                else None
            ),
            "foreign_buy_streak": self.foreign_buy_streak,
            "foreign_sell_streak": self.foreign_sell_streak,
            "banking_sector_vs_ihsg": (
                round(self.banking_sector_vs_ihsg, 4)
                if self.banking_sector_vs_ihsg is not None
                else None
            ),
            "sector_breadth": (
                round(self.sector_breadth, 4) if self.sector_breadth is not None else None
            ),
            "forward_ihsg_return_5d": (
                round(self.forward_ihsg_return_5d, 4)
                if self.forward_ihsg_return_5d is not None
                else None
            ),
            "forward_ihsg_return_10d": (
                round(self.forward_ihsg_return_10d, 4)
                if self.forward_ihsg_return_10d is not None
                else None
            ),
            "forward_ihsg_return_20d": (
                round(self.forward_ihsg_return_20d, 4)
                if self.forward_ihsg_return_20d is not None
                else None
            ),
        }

    def detection_inputs_dict(self) -> dict:
        """Return only the raw detection inputs (no regime output, no forward labels) for
        fingerprint storage."""
        return {
            "ihsg_20d_return": (
                round(self.ihsg_20d_return, 4) if self.ihsg_20d_return is not None else None
            ),
            "ihsg_trend_structure": self.ihsg_trend_structure,
            "ihsg_breadth_pct_above_ma": (
                round(self.ihsg_breadth_pct_above_ma, 4)
                if self.ihsg_breadth_pct_above_ma is not None
                else None
            ),
            "ihsg_volume_trend": (
                round(self.ihsg_volume_trend, 4) if self.ihsg_volume_trend is not None else None
            ),
            "ihsg_atr_pct": round(self.ihsg_atr_pct, 4) if self.ihsg_atr_pct is not None else None,
            "idx_foreign_flow_5d": (
                round(self.idx_foreign_flow_5d, 2) if self.idx_foreign_flow_5d is not None else None
            ),
            "idx_foreign_flow_20d": (
                round(self.idx_foreign_flow_20d, 2)
                if self.idx_foreign_flow_20d is not None
                else None
            ),
            "foreign_buy_streak": self.foreign_buy_streak,
            "foreign_sell_streak": self.foreign_sell_streak,
            "banking_sector_vs_ihsg": (
                round(self.banking_sector_vs_ihsg, 4)
                if self.banking_sector_vs_ihsg is not None
                else None
            ),
            "sector_breadth": (
                round(self.sector_breadth, 4) if self.sector_breadth is not None else None
            ),
        }
