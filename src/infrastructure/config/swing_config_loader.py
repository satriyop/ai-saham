"""
YAML loading and split-config composition for swing workflow calibration.

Layer: Infrastructure
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.application.dto.swing_config import SetupTargetConfig, SwingConfig
from src.application.services.setup_phase_config import (
    SetupPhaseConfig,
    SetupPhaseRequirementConfig,
    SetupPhaseRSPolicyConfig,
    SetupPhaseThresholdsConfig,
    VolumeTriggerValidityConfig,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.config.app_config import APP_CFG

ACCUMULATION_SCREENER_CONFIG_PATH = Path(APP_CFG.config_paths.accumulation_screener)
SWING_SETUPS_CONFIG_PATH = Path(APP_CFG.config_paths.swing_setups)
SWING_TARGETS_CONFIG_PATH = Path(APP_CFG.config_paths.swing_targets)
SWING_RISK_POLICY_CONFIG_PATH = Path(APP_CFG.config_paths.swing_risk_policy)


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
        setup_phase = data.get("setup_phase") or {}

        def _f(d: dict, k: str, default: float) -> float:
            return float(d[k]) if k in d else default

        def _i(d: dict, k: str, default: int) -> int:
            return int(d[k]) if k in d else default

        def _s(d: dict, k: str, default: str) -> str:
            return str(d[k]) if k in d else default

        def _b(d: dict, k: str, default: bool) -> bool:
            return bool(d[k]) if k in d else default

        def _phases(d: dict, k: str, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = d.get(k)
            if not isinstance(raw, list):
                return default
            return tuple(str(v).strip().upper() for v in raw if v)

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

        def _setup_phase_config(raw: Any, setups: dict) -> SetupPhaseConfig:
            if not isinstance(raw, dict):
                return defaults.setup_phase_config
            th = raw.get("thresholds") or {}
            vol = raw.get("volume_trigger") or {}
            rs_by_family = raw.get("rs_policy_by_setup_family") or {}
            requirements_raw = raw.get("requirements") or {}

            def _phase_state(name: Any) -> SetupPhaseState:
                try:
                    return SetupPhaseState(str(name).strip().upper())
                except ValueError as exc:
                    raise ValueError(
                        f"invalid setup phase name in setup_phase.requirements: {name!r}"
                    ) from exc

            def _requirement(value: Any) -> SetupPhaseRequirementConfig:
                if not isinstance(value, dict):
                    return SetupPhaseRequirementConfig()
                return SetupPhaseRequirementConfig(
                    required_sequence=tuple(
                        _phase_state(p) for p in (value.get("required_sequence") or [])
                    ),
                    enter_phases=tuple(
                        _phase_state(p) for p in (value.get("enter_phases") or [])
                    ),
                    requires_reclaim_or_pivot=_b(
                        value, "requires_reclaim_or_pivot", False
                    ),
                    entry_authority=(
                        bool(value["entry_authority"])
                        if "entry_authority" in value
                        else None
                    ),
                )

            parsed_requirements: dict[str, SetupPhaseRequirementConfig] = {}
            for fam_key, fam_val in requirements_raw.items():
                requirement = _requirement(fam_val)
                norm_key = str(fam_key).strip().lower()
                parsed_requirements[norm_key] = requirement
                parsed_requirements[norm_key.replace("-", "_")] = requirement

            for setup_key, setup_val in setups.items():
                if not isinstance(setup_val, dict):
                    continue
                family_value = str(setup_val.get("family") or "").strip().lower()
                requirement = parsed_requirements.get(
                    family_value
                ) or parsed_requirements.get(family_value.replace("-", "_"))
                if requirement is None:
                    continue
                name_key = str(setup_key).strip().lower()
                parsed_requirements.setdefault(name_key, requirement)
                parsed_requirements.setdefault(
                    name_key.replace("-", "_"), requirement
                )

            def _rs_policy(value: Any) -> SetupPhaseRSPolicyConfig:
                if not isinstance(value, dict):
                    return SetupPhaseRSPolicyConfig()
                return SetupPhaseRSPolicyConfig(
                    lag_warning_below=_f(value, "lag_warning_below", -1.0),
                    hard_exclude_below=_f(value, "hard_exclude_below", -4.0),
                    warning_max_decision=_s(value, "warning_max_decision", "WATCH"),
                    hard_exclude_max_decision=_s(
                        value, "hard_exclude_max_decision", "AVOID"
                    ),
                    mean_reversion_exception_requires_support_reclaim=_b(
                        value,
                        "mean_reversion_exception_requires_support_reclaim",
                        True,
                    ),
                )

            benchmark_sources = vol.get("trusted_benchmark_volume_sources")
            if benchmark_sources is None:
                benchmark_sources = vol.get("allowed_sources")
            if isinstance(benchmark_sources, list):
                parsed_benchmark_sources = tuple(
                    str(v).strip().lower() for v in benchmark_sources if v
                )
            else:
                parsed_benchmark_sources = (
                    defaults.setup_phase_config
                    .volume_trigger
                    .trusted_benchmark_volume_sources
                )

            return SetupPhaseConfig(
                thresholds=SetupPhaseThresholdsConfig(
                    accumulation_min_flow_score=_f(
                        th,
                        "accumulation_min_flow_score",
                        SetupPhaseThresholdsConfig().accumulation_min_flow_score,
                    ),
                    accumulation_min_flow_ratio_pct=_f(
                        th,
                        "accumulation_min_flow_ratio_pct",
                        SetupPhaseThresholdsConfig().accumulation_min_flow_ratio_pct,
                    ),
                    compression_max_bb_width_pctile=_f(
                        th,
                        "compression_max_bb_width_pctile",
                        SetupPhaseThresholdsConfig().compression_max_bb_width_pctile,
                    ),
                    breakout_min_close_above_prev_high_pct=_f(
                        th,
                        "breakout_min_close_above_prev_high_pct",
                        SetupPhaseThresholdsConfig().breakout_min_close_above_prev_high_pct,
                    ),
                    breakout_min_volume_ratio=_f(
                        th,
                        "breakout_min_volume_ratio",
                        SetupPhaseThresholdsConfig().breakout_min_volume_ratio,
                    ),
                    breakout_reclaim_vwap_min_pct=_f(
                        th,
                        "breakout_reclaim_vwap_min_pct",
                        SetupPhaseThresholdsConfig().breakout_reclaim_vwap_min_pct,
                    ),
                    exhaustion_rsi_min=_f(
                        th,
                        "exhaustion_rsi_min",
                        SetupPhaseThresholdsConfig().exhaustion_rsi_min,
                    ),
                    exhaustion_min_price_extension_pct=_f(
                        th,
                        "exhaustion_min_price_extension_pct",
                        SetupPhaseThresholdsConfig().exhaustion_min_price_extension_pct,
                    ),
                    distribution_min_bandar_score=_i(
                        th,
                        "distribution_min_bandar_score",
                        SetupPhaseThresholdsConfig().distribution_min_bandar_score,
                    ),
                    failed_max_drawdown_from_recent_high_pct=_f(
                        th,
                        "failed_max_drawdown_from_recent_high_pct",
                        SetupPhaseThresholdsConfig().failed_max_drawdown_from_recent_high_pct,
                    ),
                    failed_breakdown_below_support_pct=_f(
                        th,
                        "failed_breakdown_below_support_pct",
                        SetupPhaseThresholdsConfig().failed_breakdown_below_support_pct,
                    ),
                ),
                rs_policy_by_setup_family={
                    str(key): _rs_policy(value)
                    for key, value in rs_by_family.items()
                } or defaults.setup_phase_config.rs_policy_by_setup_family,
                requirements_by_family=parsed_requirements
                or defaults.setup_phase_config.requirements_by_family,
                volume_trigger=VolumeTriggerValidityConfig(
                    require_trusted_volume=_b(
                        vol,
                        "require_trusted_volume",
                        defaults.setup_phase_config.volume_trigger.require_trusted_volume,
                    ),
                    trusted_benchmark_volume_sources=parsed_benchmark_sources,
                    min_valid_20d_sessions=_i(
                        vol,
                        "min_valid_20d_sessions",
                        defaults.setup_phase_config.volume_trigger.min_valid_20d_sessions,
                    ),
                    zero_volume_tolerance=_i(
                        vol,
                        "zero_volume_tolerance",
                        defaults.setup_phase_config.volume_trigger.zero_volume_tolerance,
                    ),
                    dry_up_lookback_sessions=_i(
                        vol,
                        "dry_up_lookback_sessions",
                        defaults.setup_phase_config.volume_trigger.dry_up_lookback_sessions,
                    ),
                    dry_up_reference_sessions=_i(
                        vol,
                        "dry_up_reference_sessions",
                        defaults.setup_phase_config.volume_trigger.dry_up_reference_sessions,
                    ),
                    dry_up_max_ratio=_f(
                        vol,
                        "dry_up_max_ratio",
                        defaults.setup_phase_config.volume_trigger.dry_up_max_ratio,
                    ),
                    expansion_min_ratio=_f(
                        vol,
                        "expansion_min_ratio",
                        defaults.setup_phase_config.volume_trigger.expansion_min_ratio,
                    ),
                    expansion_requires_positive_close=_b(
                        vol,
                        "expansion_requires_positive_close",
                        defaults.setup_phase_config.volume_trigger.expansion_requires_positive_close,
                    ),
                ),
            )

        sc = data.get("screener") or {}
        sb = data.get("sector_breadth") or {}

        return SwingConfig(
            min_market_cap_idr=_i(sc, "min_market_cap_idr", defaults.min_market_cap_idr),
            smart_money_brokers=_codes(sm, defaults.smart_money_brokers),
            noise_brokers=_codes(ns, defaults.noise_brokers),
            smart_weight=Decimal(str(_f(sm, "weight", float(defaults.smart_weight)))),
            noise_weight=Decimal(str(_f(ns, "weight", float(defaults.noise_weight)))),
            smart_share_threshold_pct=_f(
                bq, "smart_share_threshold_pct", defaults.smart_share_threshold_pct
            ),
            smart_sell_min_share_pct=_f(
                bq, "smart_sell_min_share_pct", defaults.smart_sell_min_share_pct
            ),
            foreign_bounce_enabled=_b(fb, "enabled", defaults.foreign_bounce_enabled),
            gate_min_foreign_flow_score=_f(
                fb_gates, "min_foreign_flow_score", defaults.gate_min_foreign_flow_score
            ),
            gate_min_vwap_discount_pct=_f(
                fb_gates, "min_vwap_discount_pct", defaults.gate_min_vwap_discount_pct
            ),
            gate_required_trend=_s(fb_gates, "required_trend", defaults.gate_required_trend),
            gate_min_flow_ratio_pct=_f(
                fb_gates, "min_flow_ratio_pct", defaults.gate_min_flow_ratio_pct
            ),
            gate_max_rsi=_f(fb_gates, "max_rsi", defaults.gate_max_rsi),
            partial_max_failed_gates=_i(
                fb, "partial_max_failed_gates", defaults.partial_max_failed_gates
            ),
            foreign_bounce_family=_s(fb, "family", defaults.foreign_bounce_family),
            foreign_bounce_entry_authority=_b(
                fb, "entry_authority", defaults.foreign_bounce_entry_authority
            ),
            foreign_bounce_can_enter_from_phases=_phases(
                fb, "can_enter_from_phases", defaults.foreign_bounce_can_enter_from_phases
            ),
            coiled_spring_enabled=_b(cs, "enabled", defaults.coiled_spring_enabled),
            coiled_spring_gate_min_foreign_flow_score=_f(
                cs_gates,
                "min_foreign_flow_score",
                defaults.coiled_spring_gate_min_foreign_flow_score,
            ),
            coiled_spring_gate_max_bb_width_pctile=_f(
                cs_gates, "max_bb_width_pctile", defaults.coiled_spring_gate_max_bb_width_pctile
            ),
            coiled_spring_gate_min_flow_ratio_pct=_f(
                cs_gates, "min_flow_ratio_pct", defaults.coiled_spring_gate_min_flow_ratio_pct
            ),
            coiled_spring_gate_max_rsi=_f(cs_gates, "max_rsi", defaults.coiled_spring_gate_max_rsi),
            coiled_spring_partial_max_failed_gates=_i(
                cs, "partial_max_failed_gates", defaults.coiled_spring_partial_max_failed_gates
            ),
            coiled_spring_family=_s(cs, "family", defaults.coiled_spring_family),
            coiled_spring_entry_authority=_b(
                cs, "entry_authority", defaults.coiled_spring_entry_authority
            ),
            coiled_spring_can_enter_from_phases=_phases(
                cs, "can_enter_from_phases", defaults.coiled_spring_can_enter_from_phases
            ),
            smart_money_confirmed_enabled=_b(
                smc, "enabled", defaults.smart_money_confirmed_enabled
            ),
            smart_money_confirmed_gate_min_foreign_flow_score=_f(
                smc_gates,
                "min_foreign_flow_score",
                defaults.smart_money_confirmed_gate_min_foreign_flow_score,
            ),
            smart_money_confirmed_gate_min_smart_flow_idr=Decimal(
                str(_f(
                    smc_gates, "min_smart_flow_idr",
                    float(defaults.smart_money_confirmed_gate_min_smart_flow_idr)
                ))
            ),
            smart_money_confirmed_gate_min_smart_share_pct=_f(
                smc_gates, "min_smart_share_pct",
                defaults.smart_money_confirmed_gate_min_smart_share_pct
            ),
            smart_money_confirmed_gate_max_noise_share_pct=_f(
                smc_gates, "max_noise_share_pct",
                defaults.smart_money_confirmed_gate_max_noise_share_pct
            ),
            smart_money_confirmed_reject_smart_net_selling=_b(
                smc_gates, "reject_smart_net_selling",
                defaults.smart_money_confirmed_reject_smart_net_selling
            ),
            smart_money_confirmed_partial_max_failed_gates=_i(
                smc, "partial_max_failed_gates",
                defaults.smart_money_confirmed_partial_max_failed_gates
            ),
            smart_money_confirmed_family=_s(smc, "family", defaults.smart_money_confirmed_family),
            smart_money_confirmed_entry_authority=_b(
                smc, "entry_authority", defaults.smart_money_confirmed_entry_authority
            ),
            smart_money_confirmed_can_enter_from_phases=_phases(
                smc, "can_enter_from_phases", defaults.smart_money_confirmed_can_enter_from_phases
            ),
            pullback_continuation_enabled=_b(pc, "enabled", defaults.pullback_continuation_enabled),
            pullback_continuation_gate_min_foreign_flow_score=_f(
                pc_gates, "min_foreign_flow_score",
                defaults.pullback_continuation_gate_min_foreign_flow_score
            ),
            pullback_continuation_gate_required_trend=_s(
                pc_gates, "required_trend",
                defaults.pullback_continuation_gate_required_trend
            ),
            pullback_continuation_gate_min_flow_ratio_pct=_f(
                pc_gates, "min_flow_ratio_pct",
                defaults.pullback_continuation_gate_min_flow_ratio_pct
            ),
            pullback_continuation_gate_min_rsi=_f(
                pc_gates, "min_rsi", defaults.pullback_continuation_gate_min_rsi
            ),
            pullback_continuation_gate_max_rsi=_f(
                pc_gates, "max_rsi", defaults.pullback_continuation_gate_max_rsi
            ),
            pullback_continuation_gate_min_vwap_discount_pct=_f(
                pc_gates, "min_vwap_discount_pct",
                defaults.pullback_continuation_gate_min_vwap_discount_pct
            ),
            pullback_continuation_partial_max_failed_gates=_i(
                pc, "partial_max_failed_gates",
                defaults.pullback_continuation_partial_max_failed_gates
            ),
            pullback_continuation_family=_s(pc, "family", defaults.pullback_continuation_family),
            pullback_continuation_entry_authority=_b(
                pc, "entry_authority", defaults.pullback_continuation_entry_authority
            ),
            pullback_continuation_can_enter_from_phases=_phases(
                pc, "can_enter_from_phases", defaults.pullback_continuation_can_enter_from_phases
            ),
            enter_min_score=_f(vd, "enter_min_score", defaults.enter_min_score),
            watch_min_score=_f(vd, "watch_min_score", defaults.watch_min_score),
            strong_min_score=_f(vd_sig, "strong_min_score", defaults.strong_min_score),
            strong_min_streak=_i(vd_sig, "strong_min_streak", defaults.strong_min_streak),
            building_min_score=_f(vd_sig, "building_min_score", defaults.building_min_score),
            building_min_streak=_i(vd_sig, "building_min_streak", defaults.building_min_streak),
            coiled_spring_bb_pctile=_f(
                vd_sig, "coiled_spring_bb_pctile", defaults.coiled_spring_bb_pctile
            ),
            coiled_spring_min_score=_f(
                vd_sig, "coiled_spring_min_score", defaults.coiled_spring_min_score
            ),
            tier1_broker_codes=frozenset(_codes(t1, tuple(defaults.tier1_broker_codes))),
            bci_cluster_min_count=_i(t1, "cluster_min_count", defaults.bci_cluster_min_count),
            bci_stable_min_count=_i(t1, "stable_min_count", defaults.bci_stable_min_count),
            setup_targets=_setup_targets(data.get("setup_targets")),
            sector_breadth_enabled=_b(sb, "enabled", defaults.sector_breadth_enabled),
            sector_breadth_threshold=_f(sb, "breadth_threshold", defaults.sector_breadth_threshold),
            sector_breadth_bonus_pts=_f(sb, "bonus_pts", defaults.sector_breadth_bonus_pts),
            sector_breadth_min_tickers=_i(
                sb, "min_tickers_for_breadth", defaults.sector_breadth_min_tickers
            ),
            resistance_gate_enabled=_b(resistance, "enabled", defaults.resistance_gate_enabled),
            resistance_headroom_min_pct=_f(
                resistance, "headroom_min_pct", defaults.resistance_headroom_min_pct
            ),
            ex_date_warning_days=_i(
                corporate_actions, "ex_date_warning_days", defaults.ex_date_warning_days
            ),
            setup_phase_config=_setup_phase_config(setup_phase, setups),
        )
    except ValueError as exc:
        # An invalid setup phase name (e.g. a typo in setup_phase.requirements)
        # must fail loudly rather than silently degrade to default phase
        # requirements/entry-authority rules — a misconfigured guardrail that
        # "looks like it loaded" is worse than one that errors. Every other
        # malformed field in this loader (bad numeric strings, etc.) keeps the
        # existing fail-soft-to-defaults contract.
        if "invalid setup phase name" in str(exc):
            raise
        return defaults
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

    for path, keys in (
        (
            SWING_SETUPS_CONFIG_PATH,
            ("setups", "setup_targets", "resistance", "corporate_actions", "setup_phase"),
        ),
        (
            SWING_TARGETS_CONFIG_PATH,
            ("setups", "setup_targets", "resistance", "corporate_actions"),
        ),
        (
            SWING_RISK_POLICY_CONFIG_PATH,
            ("setups", "setup_targets", "resistance", "corporate_actions"),
        ),
    ):
        raw = _read_yaml(path)
        for key in keys:
            _merge_section(data, raw, key)

    return data
