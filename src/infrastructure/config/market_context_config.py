"""
Market Context Engine calibration config — loaded from config/market_context_engine.yaml.

Layer: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.infrastructure.config.app_config import APP_CFG

MARKET_CONTEXT_CONFIG_PATH = Path(APP_CFG.config_paths.market_context_engine)


@dataclass(frozen=True)
class VixFactorConfig:
    enabled: bool = True
    weight: float = 0.20
    ticker: str = "^VIX"
    very_low: float = 15.0    # ≤ → score 1.0
    low: float = 20.0         # (15, 20] → score 0.75
    elevated: float = 25.0   # (20, 25] → score 0.50; (25, 35] → score 0.25
    high: float = 35.0        # > → score 0.0 + VOLATILE override


@dataclass(frozen=True)
class EidoFactorConfig:
    enabled: bool = True
    weight: float = 0.20
    ticker: str = "EIDO"
    premium_pct: float = 1.0    # EIDO outperforms IHSG 5d return by > pct → score 1.0
    discount_pct: float = -2.0  # EIDO underperforms IHSG 5d return by > pct → score 0.0
    lookback_days: int = 5


@dataclass(frozen=True)
class UsdIdrFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    ticker: str = "IDR=X"
    strengthen_pct: float = -1.0  # Rupiah strengthens > 1% (negative = stronger IDR) → score 1.0
    weaken_pct: float = 2.5       # Rupiah weakens > 2.5% → score 0.0
    lookback_days: int = 5


@dataclass(frozen=True)
class IdxTrendFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    benchmark_ticker: str = "^JKSE"
    sma_fast: int = 20
    sma_slow: int = 50
    # Distance from SMA50 scoring (pct of SMA50 price)
    above_pct_strong: float = 3.0   # > +3% above SMA50 → score 1.0
    below_pct_strong: float = -5.0  # > -5% below SMA50 → score 0.0


@dataclass(frozen=True)
class IdxBreadthFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    above_sma_period: int = 20
    bullish_pct: float = 65.0    # ≥ 65% above SMA20 → score 1.0
    bearish_pct: float = 35.0    # ≤ 35% above SMA20 → score 0.0


@dataclass(frozen=True)
class ForeignFlowFactorConfig:
    enabled: bool = True
    weight: float = 0.15
    lookback_days: int = 5
    reference_days: int = 20


@dataclass(frozen=True)
class CommodityCompositeConfig:
    enabled: bool = False   # off by default
    weight: float = 0.05
    cpo_ticker: str = "KO=F"
    cpo_weight: float = 0.60
    coal_ticker: str = "MTF=F"
    coal_weight: float = 0.40
    lookback_days: int = 20
    drawdown_risk_off_pct: float = -5.0   # composite return < -5% → score 0.0
    rally_risk_on_pct: float = 5.0        # composite return > +5% → score 1.0


@dataclass(frozen=True)
class RegimeThresholds:
    risk_on_min_score: float = 0.65
    risk_off_max_score: float = 0.35
    volatile_vix_override: float = 35.0   # VIX > threshold forces VOLATILE


@dataclass(frozen=True)
class RegimeEffect:
    signal_multiplier: float = 1.0
    gate_tightening: bool = False


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
    regime_effects: dict[str, RegimeEffect] = field(default_factory=lambda: {
        "RISK_ON":  RegimeEffect(signal_multiplier=1.0, gate_tightening=False),
        "NEUTRAL":  RegimeEffect(signal_multiplier=1.0, gate_tightening=False),
        "RISK_OFF": RegimeEffect(signal_multiplier=0.60, gate_tightening=True),
        "VOLATILE": RegimeEffect(signal_multiplier=0.50, gate_tightening=True),
    })

    def get_effect(self, regime_name: str) -> RegimeEffect:
        return self.regime_effects.get(regime_name, RegimeEffect())


def load_market_context_config(
    config_path: Path = MARKET_CONTEXT_CONFIG_PATH,
) -> MarketContextConfig:
    """Load MCE config from YAML. Returns defaults on any error."""
    defaults = MarketContextConfig()
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return defaults

    try:
        root = data.get("market_context_engine", {})
        factors = root.get("factors", {})
        rt = root.get("regime_thresholds", {})
        re_cfg = root.get("regime_effects", {})

        def _vix(f: dict) -> VixFactorConfig:
            d = defaults.vix
            return VixFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                ticker=f.get("ticker", d.ticker),
                very_low=f.get("thresholds", {}).get("very_low", d.very_low),
                low=f.get("thresholds", {}).get("low", d.low),
                elevated=f.get("thresholds", {}).get("elevated", d.elevated),
                high=f.get("thresholds", {}).get("high", d.high),
            )

        def _eido(f: dict) -> EidoFactorConfig:
            d = defaults.eido
            return EidoFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                ticker=f.get("ticker", d.ticker),
                premium_pct=f.get("thresholds", {}).get("premium_pct", d.premium_pct),
                discount_pct=f.get("thresholds", {}).get("discount_pct", d.discount_pct),
                lookback_days=f.get("thresholds", {}).get("lookback_days", d.lookback_days),
            )

        def _usd_idr(f: dict) -> UsdIdrFactorConfig:
            d = defaults.usd_idr
            return UsdIdrFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                ticker=f.get("ticker", d.ticker),
                strengthen_pct=f.get("thresholds", {}).get("strengthen_pct", d.strengthen_pct),
                weaken_pct=f.get("thresholds", {}).get("weaken_pct", d.weaken_pct),
                lookback_days=f.get("thresholds", {}).get("lookback_days", d.lookback_days),
            )

        def _idx_trend(f: dict) -> IdxTrendFactorConfig:
            d = defaults.idx_trend
            return IdxTrendFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                benchmark_ticker=f.get("benchmark_ticker", d.benchmark_ticker),
                sma_fast=f.get("thresholds", {}).get("sma_fast", d.sma_fast),
                sma_slow=f.get("thresholds", {}).get("sma_slow", d.sma_slow),
                above_pct_strong=f.get("thresholds", {}).get("above_pct_strong", d.above_pct_strong),
                below_pct_strong=f.get("thresholds", {}).get("below_pct_strong", d.below_pct_strong),
            )

        def _idx_breadth(f: dict) -> IdxBreadthFactorConfig:
            d = defaults.idx_breadth
            return IdxBreadthFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                above_sma_period=f.get("thresholds", {}).get("above_sma_period", d.above_sma_period),
                bullish_pct=f.get("thresholds", {}).get("bullish_pct", d.bullish_pct),
                bearish_pct=f.get("thresholds", {}).get("bearish_pct", d.bearish_pct),
            )

        def _foreign_flow(f: dict) -> ForeignFlowFactorConfig:
            d = defaults.foreign_flow
            return ForeignFlowFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                lookback_days=f.get("thresholds", {}).get("lookback_days", d.lookback_days),
                reference_days=f.get("thresholds", {}).get("reference_days", d.reference_days),
            )

        def _commodity(f: dict) -> CommodityCompositeConfig:
            d = defaults.commodity
            comps = f.get("components", [])
            cpo_ticker = d.cpo_ticker
            cpo_weight = d.cpo_weight
            coal_ticker = d.coal_ticker
            coal_weight = d.coal_weight
            for c in comps:
                if "KO" in c.get("ticker", ""):
                    cpo_ticker = c["ticker"]
                    cpo_weight = c.get("weight", d.cpo_weight)
                else:
                    coal_ticker = c.get("ticker", d.coal_ticker)
                    coal_weight = c.get("weight", d.coal_weight)
            return CommodityCompositeConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                cpo_ticker=cpo_ticker,
                cpo_weight=cpo_weight,
                coal_ticker=coal_ticker,
                coal_weight=coal_weight,
                lookback_days=f.get("thresholds", {}).get("lookback_days", d.lookback_days),
                drawdown_risk_off_pct=f.get("thresholds", {}).get("drawdown_risk_off_pct", d.drawdown_risk_off_pct),
                rally_risk_on_pct=f.get("thresholds", {}).get("rally_risk_on_pct", d.rally_risk_on_pct),
            )

        def _re(name: str) -> RegimeEffect:
            d = defaults.regime_effects.get(name, RegimeEffect())
            cfg = re_cfg.get(name, {})
            return RegimeEffect(
                signal_multiplier=cfg.get("signal_multiplier", d.signal_multiplier),
                gate_tightening=cfg.get("gate_tightening", d.gate_tightening),
            )

        return MarketContextConfig(
            vix=_vix(factors.get("vix", {})),
            eido=_eido(factors.get("eido", {})),
            usd_idr=_usd_idr(factors.get("usd_idr", {})),
            idx_trend=_idx_trend(factors.get("idx_trend", {})),
            idx_breadth=_idx_breadth(factors.get("idx_breadth", {})),
            foreign_flow=_foreign_flow(factors.get("foreign_flow", {})),
            commodity=_commodity(factors.get("commodity_composite", {})),
            regime_thresholds=RegimeThresholds(
                risk_on_min_score=rt.get("risk_on_min_score", defaults.regime_thresholds.risk_on_min_score),
                risk_off_max_score=rt.get("risk_off_max_score", defaults.regime_thresholds.risk_off_max_score),
                volatile_vix_override=rt.get("volatile_vix_override", defaults.regime_thresholds.volatile_vix_override),
            ),
            regime_effects={
                "RISK_ON":  _re("RISK_ON"),
                "NEUTRAL":  _re("NEUTRAL"),
                "RISK_OFF": _re("RISK_OFF"),
                "VOLATILE": _re("VOLATILE"),
            },
        )
    except Exception:
        return defaults
