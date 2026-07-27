"""
Market Context Engine calibration config — loaded from config/market_context_engine.yaml.

Config dataclasses live in src.application.config.market_context_config; this
module only loads YAML and instantiates them. Re-exported here for backward
compatibility so existing `from src.infrastructure.config.market_context_config
import X` call sites keep working.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.config.market_context_config import (
    CommodityCompositeConfig,
    EidoFactorConfig,
    ForeignFlowFactorConfig,
    IdxBreadthFactorConfig,
    IdxTrendFactorConfig,
    MarketContextConfig,
    MarketContextFetchConfig,
    MarketContextScoringConfig,
    RegimeEffect,
    RegimeThresholds,
    ScoreLabelThresholds,
    UsdIdrFactorConfig,
    VixFactorConfig,
)
from src.infrastructure.config.app_config import AppConfig, load_app_config

__all__ = [
    "default_market_context_config_path",
    "VixFactorConfig",
    "EidoFactorConfig",
    "UsdIdrFactorConfig",
    "IdxTrendFactorConfig",
    "IdxBreadthFactorConfig",
    "ForeignFlowFactorConfig",
    "CommodityCompositeConfig",
    "RegimeThresholds",
    "RegimeEffect",
    "ScoreLabelThresholds",
    "MarketContextScoringConfig",
    "MarketContextFetchConfig",
    "MarketContextConfig",
    "load_market_context_config",
    "get_global_context_tickers",
]


def default_market_context_config_path(config: AppConfig | None = None) -> Path:
    cfg = config or load_app_config()
    return Path(cfg.config_paths.market_context_engine)


def load_market_context_config(
    config_path: Path | None = None,
) -> MarketContextConfig:
    """Load MCE config from YAML. Returns defaults on any error."""
    if config_path is None:
        config_path = default_market_context_config_path()
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
        fetch_cfg = root.get("fetch", {})

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
                very_low_score=f.get("score_anchors", {}).get("very_low", d.very_low_score),
                low_score=f.get("score_anchors", {}).get("low", d.low_score),
                elevated_score=f.get("score_anchors", {}).get("elevated", d.elevated_score),
                risk_off_score=f.get("score_anchors", {}).get("risk_off", d.risk_off_score),
                high_score=f.get("score_anchors", {}).get("high", d.high_score),
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
            th = f.get("thresholds", {})
            return IdxTrendFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                benchmark_ticker=f.get("benchmark_ticker", d.benchmark_ticker),
                sma_fast=th.get("sma_fast", d.sma_fast),
                sma_slow=th.get("sma_slow", d.sma_slow),
                above_pct_strong=th.get("above_pct_strong", d.above_pct_strong),
                below_pct_strong=th.get("below_pct_strong", d.below_pct_strong),
                fast_sma_adjustment=th.get("fast_sma_adjustment", d.fast_sma_adjustment),
            )

        def _idx_breadth(f: dict) -> IdxBreadthFactorConfig:
            d = defaults.idx_breadth
            th = f.get("thresholds", {})
            return IdxBreadthFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                above_sma_period=th.get("above_sma_period", d.above_sma_period),
                bullish_pct=th.get("bullish_pct", d.bullish_pct),
                bearish_pct=th.get("bearish_pct", d.bearish_pct),
            )

        def _foreign_flow(f: dict) -> ForeignFlowFactorConfig:
            d = defaults.foreign_flow
            th = f.get("thresholds", {})
            return ForeignFlowFactorConfig(
                enabled=f.get("enabled", d.enabled),
                weight=f.get("weight", d.weight),
                lookback_days=th.get("lookback_days", d.lookback_days),
                reference_days=th.get("reference_days", d.reference_days),
                bearish_diff_ratio=th.get("bearish_diff_ratio", d.bearish_diff_ratio),
                bullish_diff_ratio=th.get("bullish_diff_ratio", d.bullish_diff_ratio),
            )

        def _commodity(f: dict) -> CommodityCompositeConfig:
            d = defaults.commodity
            th = f.get("thresholds", {})
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
                lookback_days=th.get("lookback_days", d.lookback_days),
                drawdown_risk_off_pct=th.get("drawdown_risk_off_pct", d.drawdown_risk_off_pct),
                rally_risk_on_pct=th.get("rally_risk_on_pct", d.rally_risk_on_pct),
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
                risk_on_min_score=rt.get(
                    "risk_on_min_score",
                    defaults.regime_thresholds.risk_on_min_score,
                ),
                risk_off_max_score=rt.get(
                    "risk_off_max_score",
                    defaults.regime_thresholds.risk_off_max_score,
                ),
                volatile_vix_override=rt.get(
                    "volatile_vix_override",
                    defaults.regime_thresholds.volatile_vix_override,
                ),
            ),
            scoring=MarketContextScoringConfig(
                neutral_score=root.get("scoring", {}).get(
                    "neutral_score",
                    defaults.scoring.neutral_score,
                ),
                stale_business_day_gap=root.get("scoring", {}).get(
                    "stale_business_day_gap",
                    defaults.scoring.stale_business_day_gap,
                ),
                coverage_warning_unavailable_ratio=root.get("scoring", {}).get(
                    "coverage_warning_unavailable_ratio",
                    defaults.scoring.coverage_warning_unavailable_ratio,
                ),
                labels=ScoreLabelThresholds(
                    favorable_min_score=root.get("score_labels", {}).get(
                        "favorable_min_score",
                        root.get("scoring", {})
                        .get("labels", {})
                        .get(
                            "favorable_min_score",
                            defaults.scoring.labels.favorable_min_score,
                        ),
                    ),
                    neutral_min_score=root.get("score_labels", {}).get(
                        "neutral_min_score",
                        root.get("scoring", {})
                        .get("labels", {})
                        .get(
                            "neutral_min_score",
                            defaults.scoring.labels.neutral_min_score,
                        ),
                    ),
                ),
            ),
            fetch=MarketContextFetchConfig(
                global_context_end_tolerance_days=fetch_cfg.get(
                    "global_context_end_tolerance_days",
                    defaults.fetch.global_context_end_tolerance_days,
                )
            ),
            regime_effects={
                "RISK_ON": _re("RISK_ON"),
                "NEUTRAL": _re("NEUTRAL"),
                "RISK_OFF": _re("RISK_OFF"),
                "VOLATILE": _re("VOLATILE"),
            },
        )
    except Exception:
        return defaults


def get_global_context_tickers(config_path: Path | None = None) -> set[str]:
    """Return all global context tickers configured in market_context_engine.yaml."""
    try:
        cfg = load_market_context_config(config_path)
        tickers = set()
        if cfg.vix.enabled:
            tickers.add(cfg.vix.ticker.upper().strip())
        if cfg.eido.enabled:
            tickers.add(cfg.eido.ticker.upper().strip())
        if cfg.usd_idr.enabled:
            tickers.add(cfg.usd_idr.ticker.upper().strip())
        if cfg.commodity.enabled:
            if cfg.commodity.cpo_ticker:
                tickers.add(cfg.commodity.cpo_ticker.upper().strip())
            if cfg.commodity.coal_ticker:
                tickers.add(cfg.commodity.coal_ticker.upper().strip())
        return tickers
    except Exception:
        # Fallback to defaults on error
        return {"^VIX", "EIDO", "IDR=X"}
