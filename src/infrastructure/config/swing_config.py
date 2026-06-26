"""
Swing workflow calibration config loaded from responsibility-specific YAML files.

Shared between swing_commands and accumulation_commands to avoid circular imports.

Layer: Infrastructure
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.infrastructure.config.app_config import APP_CFG

ACCUMULATION_SCREENER_CONFIG_PATH = Path(APP_CFG.config_paths.accumulation_screener)
SWING_SETUPS_CONFIG_PATH = Path(APP_CFG.config_paths.swing_setups)
SWING_TARGETS_CONFIG_PATH = Path(APP_CFG.config_paths.swing_targets)
SWING_RISK_POLICY_CONFIG_PATH = Path(APP_CFG.config_paths.swing_risk_policy)


@dataclass(frozen=True)
class SetupTargetConfig:
    take_profit_pct: Decimal = Decimal("5")
    stop_loss_pct: Decimal = Decimal("5")


@dataclass(frozen=True)
class SwingConfig:
    """Swing workflow calibration params. All fields carry hardcoded defaults so
    the system works even when optional YAML policy files are absent or malformed."""

    # broker quality
    smart_money_brokers: tuple[str, ...] = ("AK", "BK", "KZ", "ZP", "RX", "MS", "DB", "ML", "YU")
    noise_brokers: tuple[str, ...] = ("YP", "PD", "XL", "XC")
    smart_weight: Decimal = Decimal("1.5")
    noise_weight: Decimal = Decimal("0.5")
    smart_share_threshold_pct: float = 60.0
    smart_sell_min_share_pct: float = 15.0
    # foreign_bounce setup gates
    foreign_bounce_enabled: bool = True
    gate_min_score: float = 70.0
    gate_min_vwap_discount_pct: float = 3.0
    gate_required_trend: str = "SIDE"
    gate_min_flow_ratio_pct: float = 5.0
    gate_max_rsi: float = 60.0
    partial_max_failed_gates: int = 2
    # coiled_spring setup gates
    coiled_spring_enabled: bool = True
    coiled_spring_gate_min_score: float = 60.0
    coiled_spring_gate_max_bb_width_pctile: float = 0.20
    coiled_spring_gate_min_flow_ratio_pct: float = 3.0
    coiled_spring_gate_max_rsi: float = 65.0
    coiled_spring_partial_max_failed_gates: int = 2
    # smart_money_confirmed setup gates
    smart_money_confirmed_enabled: bool = True
    smart_money_confirmed_gate_min_score: float = 60.0
    smart_money_confirmed_gate_min_smart_flow_idr: Decimal = Decimal("0")
    smart_money_confirmed_gate_min_smart_share_pct: float = 30.0
    smart_money_confirmed_gate_max_noise_share_pct: float = 60.0
    smart_money_confirmed_reject_smart_net_selling: bool = True
    smart_money_confirmed_partial_max_failed_gates: int = 1
    # pullback_continuation setup gates
    pullback_continuation_enabled: bool = True
    pullback_continuation_gate_min_score: float = 55.0
    pullback_continuation_gate_required_trend: str = "UP"
    pullback_continuation_gate_min_flow_ratio_pct: float = 2.0
    pullback_continuation_gate_min_rsi: float = 40.0
    pullback_continuation_gate_max_rsi: float = 65.0
    pullback_continuation_gate_min_vwap_discount_pct: float = -2.0
    pullback_continuation_partial_max_failed_gates: int = 2
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
    # regime-adaptive setup exits
    setup_targets: dict[str, SetupTargetConfig] = field(default_factory=lambda: {
        "risk_on": SetupTargetConfig(Decimal("8"), Decimal("4")),
        "neutral": SetupTargetConfig(Decimal("5"), Decimal("5")),
        "volatile": SetupTargetConfig(Decimal("3"), Decimal("3")),
        "risk_off": SetupTargetConfig(Decimal("3"), Decimal("3")),
        "default": SetupTargetConfig(Decimal("5"), Decimal("5")),
    })
    # sector breadth confirmation (accumulation_screener.yaml)
    sector_breadth_enabled: bool = True
    sector_breadth_threshold: float = 0.60
    sector_breadth_bonus_pts: float = 10.0
    sector_breadth_min_tickers: int = 3
    # resistance/corporate-action gates
    resistance_gate_enabled: bool = True
    resistance_headroom_min_pct: float = 5.0
    ex_date_warning_days: int = 10


def load_swing_config(
    config_path: Path | None = None,
) -> SwingConfig:
    """Load swing workflow calibration params from YAML. Returns defaults on any error."""
    defaults = SwingConfig()
    try:
        data = _read_single_config(config_path) if config_path else _read_split_config()
    except Exception:
        return defaults
    try:
        bq = data.get("broker_quality") or {}
        sm = bq.get("smart_money") or {}
        ns = bq.get("noise") or {}
        t1 = bq.get("tier1") or {}
        setups = data.get("setups") or {}
        fb = setups.get("foreign-bounce") or data.get("foreign_bounce") or {}
        fb_gates = fb.get("gates") or {}
        cs = setups.get("coiled-spring") or {}
        cs_gates = cs.get("gates") or {}
        smc = setups.get("smart-money-confirmed") or {}
        smc_gates = smc.get("gates") or {}
        pc = setups.get("pullback-continuation") or {}
        pc_gates = pc.get("gates") or {}
        vd = data.get("verdicts") or {}
        vd_sig = vd.get("signals") or {}
        resistance = data.get("resistance") or {}
        corporate_actions = data.get("corporate_actions") or {}

        def _f(d: dict, k: str, default: float) -> float:
            return float(d[k]) if k in d else default

        def _i(d: dict, k: str, default: int) -> int:
            return int(d[k]) if k in d else default

        def _s(d: dict, k: str, default: str) -> str:
            return str(d[k]) if k in d else default

        def _b(d: dict, k: str, default: bool) -> bool:
            return bool(d[k]) if k in d else default

        def _setup_targets(raw: Any) -> dict[str, SetupTargetConfig]:
            if not isinstance(raw, dict):
                return defaults.setup_targets
            parsed: dict[str, SetupTargetConfig] = {}
            for key, val in raw.items():
                if not isinstance(val, dict):
                    continue
                parsed[str(key).lower()] = SetupTargetConfig(
                    take_profit_pct=Decimal(str(val["take_profit_pct"])),
                    stop_loss_pct=Decimal(str(val["stop_loss_pct"])),
                )
            return parsed if parsed else defaults.setup_targets

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
            smart_sell_min_share_pct=_f(bq, "smart_sell_min_share_pct", defaults.smart_sell_min_share_pct),
            foreign_bounce_enabled=_b(fb, "enabled", defaults.foreign_bounce_enabled),
            gate_min_score=_f(fb_gates, "min_score", defaults.gate_min_score),
            gate_min_vwap_discount_pct=_f(fb_gates, "min_vwap_discount_pct", defaults.gate_min_vwap_discount_pct),
            gate_required_trend=_s(fb_gates, "required_trend", defaults.gate_required_trend),
            gate_min_flow_ratio_pct=_f(fb_gates, "min_flow_ratio_pct", defaults.gate_min_flow_ratio_pct),
            gate_max_rsi=_f(fb_gates, "max_rsi", defaults.gate_max_rsi),
            partial_max_failed_gates=_i(fb, "partial_max_failed_gates", defaults.partial_max_failed_gates),
            coiled_spring_enabled=_b(cs, "enabled", defaults.coiled_spring_enabled),
            coiled_spring_gate_min_score=_f(cs_gates, "min_score", defaults.coiled_spring_gate_min_score),
            coiled_spring_gate_max_bb_width_pctile=_f(cs_gates, "max_bb_width_pctile", defaults.coiled_spring_gate_max_bb_width_pctile),
            coiled_spring_gate_min_flow_ratio_pct=_f(cs_gates, "min_flow_ratio_pct", defaults.coiled_spring_gate_min_flow_ratio_pct),
            coiled_spring_gate_max_rsi=_f(cs_gates, "max_rsi", defaults.coiled_spring_gate_max_rsi),
            coiled_spring_partial_max_failed_gates=_i(cs, "partial_max_failed_gates", defaults.coiled_spring_partial_max_failed_gates),
            smart_money_confirmed_enabled=_b(smc, "enabled", defaults.smart_money_confirmed_enabled),
            smart_money_confirmed_gate_min_score=_f(smc_gates, "min_score", defaults.smart_money_confirmed_gate_min_score),
            smart_money_confirmed_gate_min_smart_flow_idr=Decimal(
                str(_f(smc_gates, "min_smart_flow_idr", float(defaults.smart_money_confirmed_gate_min_smart_flow_idr)))
            ),
            smart_money_confirmed_gate_min_smart_share_pct=_f(smc_gates, "min_smart_share_pct", defaults.smart_money_confirmed_gate_min_smart_share_pct),
            smart_money_confirmed_gate_max_noise_share_pct=_f(smc_gates, "max_noise_share_pct", defaults.smart_money_confirmed_gate_max_noise_share_pct),
            smart_money_confirmed_reject_smart_net_selling=_b(smc_gates, "reject_smart_net_selling", defaults.smart_money_confirmed_reject_smart_net_selling),
            smart_money_confirmed_partial_max_failed_gates=_i(smc, "partial_max_failed_gates", defaults.smart_money_confirmed_partial_max_failed_gates),
            pullback_continuation_enabled=_b(pc, "enabled", defaults.pullback_continuation_enabled),
            pullback_continuation_gate_min_score=_f(pc_gates, "min_score", defaults.pullback_continuation_gate_min_score),
            pullback_continuation_gate_required_trend=_s(pc_gates, "required_trend", defaults.pullback_continuation_gate_required_trend),
            pullback_continuation_gate_min_flow_ratio_pct=_f(pc_gates, "min_flow_ratio_pct", defaults.pullback_continuation_gate_min_flow_ratio_pct),
            pullback_continuation_gate_min_rsi=_f(pc_gates, "min_rsi", defaults.pullback_continuation_gate_min_rsi),
            pullback_continuation_gate_max_rsi=_f(pc_gates, "max_rsi", defaults.pullback_continuation_gate_max_rsi),
            pullback_continuation_gate_min_vwap_discount_pct=_f(pc_gates, "min_vwap_discount_pct", defaults.pullback_continuation_gate_min_vwap_discount_pct),
            pullback_continuation_partial_max_failed_gates=_i(pc, "partial_max_failed_gates", defaults.pullback_continuation_partial_max_failed_gates),
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
            setup_targets=_setup_targets(data.get("setup_targets")),
            sector_breadth_enabled=_b(sb, "enabled", defaults.sector_breadth_enabled),
            sector_breadth_threshold=_f(sb, "breadth_threshold", defaults.sector_breadth_threshold),
            sector_breadth_bonus_pts=_f(sb, "bonus_pts", defaults.sector_breadth_bonus_pts),
            sector_breadth_min_tickers=_i(sb, "min_tickers_for_breadth", defaults.sector_breadth_min_tickers),
            resistance_gate_enabled=_b(resistance, "enabled", defaults.resistance_gate_enabled),
            resistance_headroom_min_pct=_f(resistance, "headroom_min_pct", defaults.resistance_headroom_min_pct),
            ex_date_warning_days=_i(corporate_actions, "ex_date_warning_days", defaults.ex_date_warning_days),
        )
    except Exception:
        return defaults


def _read_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _merge_section(data: dict, raw: dict, key: str) -> None:
    section = raw.get(key)
    if isinstance(section, dict):
        data[key] = section


def _read_single_config(config_path: Path | None) -> dict:
    return _read_yaml(config_path) if config_path else {}


def _read_split_config() -> dict:
    data: dict[str, Any] = {}

    accumulation_raw = _read_yaml(ACCUMULATION_SCREENER_CONFIG_PATH)
    accumulation = accumulation_raw.get("accumulation_screener") or accumulation_raw
    if isinstance(accumulation, dict):
        for key in ("screener", "sector_breadth", "broker_quality", "verdicts"):
            _merge_section(data, accumulation, key)

    for path in (
        SWING_SETUPS_CONFIG_PATH,
        SWING_TARGETS_CONFIG_PATH,
        SWING_RISK_POLICY_CONFIG_PATH,
    ):
        raw = _read_yaml(path)
        for key in ("setups", "setup_targets", "resistance", "corporate_actions"):
            _merge_section(data, raw, key)

    return data
