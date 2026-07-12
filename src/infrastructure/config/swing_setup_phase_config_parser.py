"""
Parser for setup phase configurations including requirements, RS policies, and volume triggers.

Layer: Infrastructure
"""

from typing import Any

from src.application.dto.swing_config import SwingConfig
from src.application.services.setup_phase_config import (
    SetupPhaseConfig,
    SetupPhaseRequirementConfig,
    SetupPhaseRSPolicyConfig,
    SetupPhaseThresholdsConfig,
    VolumeTriggerValidityConfig,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.config.swing_config_primitives import (
    bool_or_default,
    float_or_default,
    int_or_default,
    str_or_default,
)


def parse_setup_phase_config(
    raw: Any,
    setups: dict,
    defaults: SwingConfig,
) -> SetupPhaseConfig:
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
            requires_reclaim_or_pivot=bool_or_default(
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
            lag_warning_below=float_or_default(value, "lag_warning_below", -1.0),
            hard_exclude_below=float_or_default(value, "hard_exclude_below", -4.0),
            warning_max_decision=str_or_default(value, "warning_max_decision", "WATCH"),
            hard_exclude_max_decision=str_or_default(
                value, "hard_exclude_max_decision", "AVOID"
            ),
            mean_reversion_exception_requires_support_reclaim=bool_or_default(
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
            accumulation_min_flow_score=float_or_default(
                th,
                "accumulation_min_flow_score",
                defaults.setup_phase_config.thresholds.accumulation_min_flow_score,
            ),
            accumulation_min_flow_ratio_pct=float_or_default(
                th,
                "accumulation_min_flow_ratio_pct",
                defaults.setup_phase_config.thresholds.accumulation_min_flow_ratio_pct,
            ),
            compression_max_bb_width_pctile=float_or_default(
                th,
                "compression_max_bb_width_pctile",
                defaults.setup_phase_config.thresholds.compression_max_bb_width_pctile,
            ),
            breakout_min_close_above_prev_high_pct=float_or_default(
                th,
                "breakout_min_close_above_prev_high_pct",
                defaults.setup_phase_config.thresholds.breakout_min_close_above_prev_high_pct,
            ),
            breakout_min_volume_ratio=float_or_default(
                th,
                "breakout_min_volume_ratio",
                defaults.setup_phase_config.thresholds.breakout_min_volume_ratio,
            ),
            breakout_reclaim_vwap_min_pct=float_or_default(
                th,
                "breakout_reclaim_vwap_min_pct",
                defaults.setup_phase_config.thresholds.breakout_reclaim_vwap_min_pct,
            ),
            exhaustion_rsi_min=float_or_default(
                th,
                "exhaustion_rsi_min",
                defaults.setup_phase_config.thresholds.exhaustion_rsi_min,
            ),
            exhaustion_min_price_extension_pct=float_or_default(
                th,
                "exhaustion_min_price_extension_pct",
                defaults.setup_phase_config.thresholds.exhaustion_min_price_extension_pct,
            ),
            distribution_min_bandar_score=int_or_default(
                th,
                "distribution_min_bandar_score",
                defaults.setup_phase_config.thresholds.distribution_min_bandar_score,
            ),
            failed_max_drawdown_from_recent_high_pct=float_or_default(
                th,
                "failed_max_drawdown_from_recent_high_pct",
                defaults.setup_phase_config.thresholds.failed_max_drawdown_from_recent_high_pct,
            ),
            failed_breakdown_below_support_pct=float_or_default(
                th,
                "failed_breakdown_below_support_pct",
                defaults.setup_phase_config.thresholds.failed_breakdown_below_support_pct,
            ),
        ),
        rs_policy_by_setup_family={
            str(key): _rs_policy(value)
            for key, value in rs_by_family.items()
        } or defaults.setup_phase_config.rs_policy_by_setup_family,
        requirements_by_family=parsed_requirements
        or defaults.setup_phase_config.requirements_by_family,
        volume_trigger=VolumeTriggerValidityConfig(
            require_trusted_volume=bool_or_default(
                vol,
                "require_trusted_volume",
                defaults.setup_phase_config.volume_trigger.require_trusted_volume,
            ),
            trusted_benchmark_volume_sources=parsed_benchmark_sources,
            min_valid_20d_sessions=int_or_default(
                vol,
                "min_valid_20d_sessions",
                defaults.setup_phase_config.volume_trigger.min_valid_20d_sessions,
            ),
            zero_volume_tolerance=int_or_default(
                vol,
                "zero_volume_tolerance",
                defaults.setup_phase_config.volume_trigger.zero_volume_tolerance,
            ),
            dry_up_lookback_sessions=int_or_default(
                vol,
                "dry_up_lookback_sessions",
                defaults.setup_phase_config.volume_trigger.dry_up_lookback_sessions,
            ),
            dry_up_reference_sessions=int_or_default(
                vol,
                "dry_up_reference_sessions",
                defaults.setup_phase_config.volume_trigger.dry_up_reference_sessions,
            ),
            dry_up_max_ratio=float_or_default(
                vol,
                "dry_up_max_ratio",
                defaults.setup_phase_config.volume_trigger.dry_up_max_ratio,
            ),
            expansion_min_ratio=float_or_default(
                vol,
                "expansion_min_ratio",
                defaults.setup_phase_config.volume_trigger.expansion_min_ratio,
            ),
            expansion_requires_positive_close=bool_or_default(
                vol,
                "expansion_requires_positive_close",
                defaults.setup_phase_config.volume_trigger.expansion_requires_positive_close,
            ),
        ),
    )
