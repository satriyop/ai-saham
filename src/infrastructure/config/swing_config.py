"""
Swing screener calibration config — loaded from config/swing_screener.yaml.

Shared between swing_commands and accumulation_commands to avoid circular imports.

Layer: Infrastructure
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

SWING_SCREENER_CONFIG_PATH = Path("config/swing_screener.yaml")


@dataclass(frozen=True)
class SwingConfig:
    """Swing screener calibration params. All fields carry hardcoded defaults so
    the system works even when config/swing_screener.yaml is absent or malformed."""

    # broker quality
    smart_money_brokers: tuple[str, ...] = ("AK", "BK", "KZ", "ZP", "RX", "MS", "DB", "ML", "YU")
    noise_brokers: tuple[str, ...] = ("YP", "PD", "XL", "XC")
    smart_weight: Decimal = Decimal("1.5")
    noise_weight: Decimal = Decimal("0.5")
    smart_share_threshold_pct: float = 60.0
    # foreign_bounce preset gates
    gate_min_score: float = 70.0
    gate_min_vwap_discount_pct: float = 3.0
    gate_required_trend: str = "SIDE"
    gate_min_flow_ratio_pct: float = 5.0
    gate_max_rsi: float = 60.0
    watch_max_failed_gates: int = 2
    # verdict + signal label thresholds
    enter_min_score: float = 70.0
    watch_min_score: float = 40.0
    strong_min_score: float = 70.0
    strong_min_streak: int = 8
    building_min_score: float = 60.0
    building_min_streak: int = 5
    coiled_spring_bb_pctile: float = 0.20
    coiled_spring_min_score: float = 60.0
    # screener: market cap floor (0 = disabled; e.g. 500_000_000_000 = 500B IDR)
    min_market_cap_idr: int = 0
    # tier1 broker codes for BCI (Broker Concentration Index) scoring
    tier1_broker_codes: frozenset[str] = frozenset({"AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR"})
    bci_cluster_min_count: int = 3
    bci_stable_min_count: int = 1
    # market regime indicator periods (passed to MarketRegimeRequest)
    regime_breadth_sma_period: int = 20
    regime_benchmark_sma_fast: int = 20
    regime_benchmark_sma_slow: int = 50
    regime_breadth_threshold_pct: int = 50
    # sector breadth confirmation (sector_breadth section in swing_screener.yaml)
    sector_breadth_enabled: bool = True
    sector_breadth_threshold: float = 0.60
    sector_breadth_bonus_pts: float = 10.0
    sector_breadth_min_tickers: int = 3


def load_swing_config(
    config_path: Path = SWING_SCREENER_CONFIG_PATH,
) -> SwingConfig:
    """Load swing screener calibration params from YAML. Returns defaults on any error."""
    defaults = SwingConfig()
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return defaults
    try:
        bq = data.get("broker_quality") or {}
        sm = bq.get("smart_money") or {}
        ns = bq.get("noise") or {}
        t1 = bq.get("tier1") or {}
        fb = data.get("foreign_bounce") or {}
        fb_gates = fb.get("gates") or {}
        vd = data.get("verdicts") or {}
        vd_sig = vd.get("signals") or {}
        rg = data.get("regime") or {}

        def _f(d: dict, k: str, default: float) -> float:
            return float(d[k]) if k in d else default

        def _i(d: dict, k: str, default: int) -> int:
            return int(d[k]) if k in d else default

        def _s(d: dict, k: str, default: str) -> str:
            return str(d[k]) if k in d else default

        def _codes(d: dict, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = d.get("brokers") or []
            parsed = tuple(str(c).strip().upper() for c in raw if c)
            return parsed if parsed else default

        sc = data.get("screener") or {}
        sb = data.get("sector_breadth") or {}

        return SwingConfig(
            min_market_cap_idr=_i(sc, "min_market_cap_idr", defaults.min_market_cap_idr),
            smart_money_brokers=_codes(sm, defaults.smart_money_brokers),
            noise_brokers=_codes(ns, defaults.noise_brokers),
            smart_weight=Decimal(str(_f(sm, "weight", float(defaults.smart_weight)))),
            noise_weight=Decimal(str(_f(ns, "weight", float(defaults.noise_weight)))),
            smart_share_threshold_pct=_f(bq, "smart_share_threshold_pct", defaults.smart_share_threshold_pct),
            gate_min_score=_f(fb_gates, "min_score", defaults.gate_min_score),
            gate_min_vwap_discount_pct=_f(fb_gates, "min_vwap_discount_pct", defaults.gate_min_vwap_discount_pct),
            gate_required_trend=_s(fb_gates, "required_trend", defaults.gate_required_trend),
            gate_min_flow_ratio_pct=_f(fb_gates, "min_flow_ratio_pct", defaults.gate_min_flow_ratio_pct),
            gate_max_rsi=_f(fb_gates, "max_rsi", defaults.gate_max_rsi),
            watch_max_failed_gates=_i(fb, "watch_max_failed_gates", defaults.watch_max_failed_gates),
            enter_min_score=_f(vd, "enter_min_score", defaults.enter_min_score),
            watch_min_score=_f(vd, "watch_min_score", defaults.watch_min_score),
            strong_min_score=_f(vd_sig, "strong_min_score", defaults.strong_min_score),
            strong_min_streak=_i(vd_sig, "strong_min_streak", defaults.strong_min_streak),
            building_min_score=_f(vd_sig, "building_min_score", defaults.building_min_score),
            building_min_streak=_i(vd_sig, "building_min_streak", defaults.building_min_streak),
            coiled_spring_bb_pctile=_f(vd_sig, "coiled_spring_bb_pctile", defaults.coiled_spring_bb_pctile),
            coiled_spring_min_score=_f(vd_sig, "coiled_spring_min_score", defaults.coiled_spring_min_score),
            tier1_broker_codes=frozenset(_codes(t1, tuple(defaults.tier1_broker_codes))),
            bci_cluster_min_count=_i(t1, "cluster_min_count", defaults.bci_cluster_min_count),
            bci_stable_min_count=_i(t1, "stable_min_count", defaults.bci_stable_min_count),
            regime_breadth_sma_period=_i(rg, "breadth_sma_period", defaults.regime_breadth_sma_period),
            regime_benchmark_sma_fast=_i(rg, "benchmark_sma_fast", defaults.regime_benchmark_sma_fast),
            regime_benchmark_sma_slow=_i(rg, "benchmark_sma_slow", defaults.regime_benchmark_sma_slow),
            regime_breadth_threshold_pct=_i(rg, "breadth_threshold_pct", defaults.regime_breadth_threshold_pct),
            sector_breadth_enabled=bool(
                sb["sector_breadth_enabled"] if "sector_breadth_enabled" in sb
                else defaults.sector_breadth_enabled
            ),
            sector_breadth_threshold=_f(sb, "breadth_threshold", defaults.sector_breadth_threshold),
            sector_breadth_bonus_pts=_f(sb, "bonus_pts", defaults.sector_breadth_bonus_pts),
            sector_breadth_min_tickers=_i(sb, "min_tickers_for_breadth", defaults.sector_breadth_min_tickers),
        )
    except Exception:
        return defaults
