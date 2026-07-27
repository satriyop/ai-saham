"""
Market Context Engine calibration config — application-layer DTOs.

Pure dataclasses with hardcoded defaults. Infrastructure loads YAML and
instantiates these; application code (use cases, services) depends only on
this module, never on the infrastructure YAML loader.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VixFactorConfig:
    enabled: bool = True
    weight: float = 0.20
    ticker: str = "^VIX"
    very_low: float = 15.0  # ≤ → score 1.0
    low: float = 20.0  # (15, 20] → score 0.75
    elevated: float = 25.0  # (20, 25] → score 0.50; (25, 35] → score 0.25
    high: float = 35.0  # > → score 0.0 + VOLATILE override
    very_low_score: float = 1.0
    low_score: float = 0.75
    elevated_score: float = 0.50
    risk_off_score: float = 0.25
    high_score: float = 0.0


@dataclass(frozen=True)
class EidoFactorConfig:
    enabled: bool = True
    weight: float = 0.20
    ticker: str = "EIDO"
    premium_pct: float = 1.0  # EIDO outperforms IHSG 5d return by > pct → score 1.0
    discount_pct: float = -2.0  # EIDO underperforms IHSG 5d return by > pct → score 0.0
    lookback_days: int = 5


@dataclass(frozen=True)
class UsdIdrFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    ticker: str = "IDR=X"
    strengthen_pct: float = -1.0  # Rupiah strengthens > 1% (negative = stronger IDR) → score 1.0
    weaken_pct: float = 2.5  # Rupiah weakens > 2.5% → score 0.0
    lookback_days: int = 5


@dataclass(frozen=True)
class IdxTrendFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    benchmark_ticker: str = "IHSG"
    sma_fast: int = 20
    sma_slow: int = 50
    # Distance from SMA50 scoring (pct of SMA50 price)
    above_pct_strong: float = 3.0  # > +3% above SMA50 → score 1.0
    below_pct_strong: float = -5.0  # > -5% below SMA50 → score 0.0
    fast_sma_adjustment: float = 0.05


@dataclass(frozen=True)
class IdxBreadthFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    above_sma_period: int = 20
    bullish_pct: float = 65.0  # ≥ 65% above SMA20 → score 1.0
    bearish_pct: float = 35.0  # ≤ 35% above SMA20 → score 0.0


@dataclass(frozen=True)
class ForeignFlowFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    lookback_days: int = 5
    reference_days: int = 20
    bearish_diff_ratio: float = -0.5
    bullish_diff_ratio: float = 0.5


@dataclass(frozen=True)
class CommodityCompositeConfig:
    enabled: bool = False  # off by default
    weight: float = 0.05
    cpo_ticker: str = "KO=F"
    cpo_weight: float = 0.60
    coal_ticker: str = "MTF=F"
    coal_weight: float = 0.40
    lookback_days: int = 20
    drawdown_risk_off_pct: float = -5.0  # composite return < -5% → score 0.0
    rally_risk_on_pct: float = 5.0  # composite return > +5% → score 1.0


@dataclass(frozen=True)
class RegimeThresholds:
    risk_on_min_score: float = 0.65
    risk_off_max_score: float = 0.35
    volatile_vix_override: float = 35.0  # VIX > threshold forces VOLATILE


@dataclass(frozen=True)
class RegimeEffect:
    signal_multiplier: float = 1.0
    gate_tightening: bool = False


@dataclass(frozen=True)
class ScoreLabelThresholds:
    favorable_min_score: float = 0.65
    neutral_min_score: float = 0.35


@dataclass(frozen=True)
class MarketContextScoringConfig:
    neutral_score: float = 0.5
    stale_business_day_gap: int = 1
    coverage_warning_unavailable_ratio: float = 0.5
    labels: ScoreLabelThresholds = field(default_factory=ScoreLabelThresholds)


@dataclass(frozen=True)
class MarketContextFetchConfig:
    global_context_end_tolerance_days: int = 1


@dataclass(frozen=True)
class MarketContextConfig:
    """
    Full config for MarketContextEngine. All fields carry hardcoded defaults
    so the system works when config/market_context_engine.yaml is absent.
    """

    vix: VixFactorConfig = field(default_factory=VixFactorConfig)
    eido: EidoFactorConfig = field(default_factory=EidoFactorConfig)
    usd_idr: UsdIdrFactorConfig = field(default_factory=UsdIdrFactorConfig)
    idx_trend: IdxTrendFactorConfig = field(default_factory=IdxTrendFactorConfig)
    idx_breadth: IdxBreadthFactorConfig = field(default_factory=IdxBreadthFactorConfig)
    foreign_flow: ForeignFlowFactorConfig = field(default_factory=ForeignFlowFactorConfig)
    commodity: CommodityCompositeConfig = field(default_factory=CommodityCompositeConfig)
    regime_thresholds: RegimeThresholds = field(default_factory=RegimeThresholds)
    scoring: MarketContextScoringConfig = field(default_factory=MarketContextScoringConfig)
    fetch: MarketContextFetchConfig = field(default_factory=MarketContextFetchConfig)
    regime_effects: dict[str, RegimeEffect] = field(
        default_factory=lambda: {
            "RISK_ON": RegimeEffect(signal_multiplier=1.0, gate_tightening=False),
            "NEUTRAL": RegimeEffect(signal_multiplier=1.0, gate_tightening=False),
            "RISK_OFF": RegimeEffect(signal_multiplier=0.60, gate_tightening=True),
            "VOLATILE": RegimeEffect(signal_multiplier=0.50, gate_tightening=True),
        }
    )

    def get_effect(self, regime_name: str) -> RegimeEffect:
        return self.regime_effects.get(regime_name, RegimeEffect())
