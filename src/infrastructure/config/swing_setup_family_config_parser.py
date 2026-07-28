"""
Parser for setup family fields.

Layer: Infrastructure
"""

from decimal import Decimal

from src.application.dto.swing_policy_config import SwingPolicyConfig
from src.infrastructure.config.swing_policy_config_primitives import (
    bool_or_default,
    float_or_default,
    int_or_default,
    phase_names_or_default,
    str_or_default,
)


def parse_setup_family_fields(
    data: dict,
    defaults: SwingPolicyConfig,
) -> dict[str, object]:
    setups = data.get("setups") or {}
    fb = setups.get("foreign-bounce") or data.get("foreign_bounce") or {}
    fb_gates = fb.get("gates") or {}
    cs = setups.get("coiled-spring") or {}
    cs_gates = cs.get("gates") or {}
    smc = setups.get("smart-money-confirmed") or {}
    smc_gates = smc.get("gates") or {}
    pc = setups.get("pullback-continuation") or {}
    pc_gates = pc.get("gates") or {}

    return {
        "foreign_bounce_enabled": bool_or_default(fb, "enabled", defaults.foreign_bounce_enabled),
        "gate_min_accum_score": float_or_default(
            fb_gates, "min_accum_score", defaults.gate_min_accum_score
        ),
        "gate_min_vwap_discount_pct": float_or_default(
            fb_gates, "min_vwap_discount_pct", defaults.gate_min_vwap_discount_pct
        ),
        "gate_required_trend": str_or_default(
            fb_gates, "required_trend", defaults.gate_required_trend
        ),
        "gate_min_flow_ratio_pct": float_or_default(
            fb_gates, "min_flow_ratio_pct", defaults.gate_min_flow_ratio_pct
        ),
        "gate_max_rsi": float_or_default(fb_gates, "max_rsi", defaults.gate_max_rsi),
        "partial_max_failed_gates": int_or_default(
            fb, "partial_max_failed_gates", defaults.partial_max_failed_gates
        ),
        "foreign_bounce_family": str_or_default(fb, "family", defaults.foreign_bounce_family),
        "foreign_bounce_entry_authority": bool_or_default(
            fb, "entry_authority", defaults.foreign_bounce_entry_authority
        ),
        "foreign_bounce_can_enter_from_phases": phase_names_or_default(
            fb, "can_enter_from_phases", defaults.foreign_bounce_can_enter_from_phases
        ),
        "coiled_spring_enabled": bool_or_default(cs, "enabled", defaults.coiled_spring_enabled),
        "coiled_spring_gate_min_accum_score": float_or_default(
            cs_gates,
            "min_accum_score",
            defaults.coiled_spring_gate_min_accum_score,
        ),
        "coiled_spring_gate_max_bb_width_pctile": float_or_default(
            cs_gates, "max_bb_width_pctile", defaults.coiled_spring_gate_max_bb_width_pctile
        ),
        "coiled_spring_gate_min_flow_ratio_pct": float_or_default(
            cs_gates, "min_flow_ratio_pct", defaults.coiled_spring_gate_min_flow_ratio_pct
        ),
        "coiled_spring_gate_max_rsi": float_or_default(
            cs_gates, "max_rsi", defaults.coiled_spring_gate_max_rsi
        ),
        "coiled_spring_partial_max_failed_gates": int_or_default(
            cs, "partial_max_failed_gates", defaults.coiled_spring_partial_max_failed_gates
        ),
        "coiled_spring_family": str_or_default(cs, "family", defaults.coiled_spring_family),
        "coiled_spring_entry_authority": bool_or_default(
            cs, "entry_authority", defaults.coiled_spring_entry_authority
        ),
        "coiled_spring_can_enter_from_phases": phase_names_or_default(
            cs, "can_enter_from_phases", defaults.coiled_spring_can_enter_from_phases
        ),
        "smart_money_confirmed_enabled": bool_or_default(
            smc, "enabled", defaults.smart_money_confirmed_enabled
        ),
        "smart_money_confirmed_gate_min_accum_score": float_or_default(
            smc_gates,
            "min_accum_score",
            defaults.smart_money_confirmed_gate_min_accum_score,
        ),
        "smart_money_confirmed_gate_min_smart_flow_idr": Decimal(
            str(
                float_or_default(
                    smc_gates,
                    "min_smart_flow_idr",
                    float(defaults.smart_money_confirmed_gate_min_smart_flow_idr),
                )
            )
        ),
        "smart_money_confirmed_gate_min_smart_share_pct": float_or_default(
            smc_gates,
            "min_smart_share_pct",
            defaults.smart_money_confirmed_gate_min_smart_share_pct,
        ),
        "smart_money_confirmed_gate_max_noise_share_pct": float_or_default(
            smc_gates,
            "max_noise_share_pct",
            defaults.smart_money_confirmed_gate_max_noise_share_pct,
        ),
        "smart_money_confirmed_reject_smart_net_selling": bool_or_default(
            smc_gates,
            "reject_smart_net_selling",
            defaults.smart_money_confirmed_reject_smart_net_selling,
        ),
        "smart_money_confirmed_partial_max_failed_gates": int_or_default(
            smc, "partial_max_failed_gates", defaults.smart_money_confirmed_partial_max_failed_gates
        ),
        "smart_money_confirmed_family": str_or_default(
            smc, "family", defaults.smart_money_confirmed_family
        ),
        "smart_money_confirmed_entry_authority": bool_or_default(
            smc, "entry_authority", defaults.smart_money_confirmed_entry_authority
        ),
        "smart_money_confirmed_can_enter_from_phases": phase_names_or_default(
            smc, "can_enter_from_phases", defaults.smart_money_confirmed_can_enter_from_phases
        ),
        "pullback_continuation_enabled": bool_or_default(
            pc, "enabled", defaults.pullback_continuation_enabled
        ),
        "pullback_continuation_gate_min_accum_score": float_or_default(
            pc_gates, "min_accum_score", defaults.pullback_continuation_gate_min_accum_score
        ),
        "pullback_continuation_gate_required_trend": str_or_default(
            pc_gates, "required_trend", defaults.pullback_continuation_gate_required_trend
        ),
        "pullback_continuation_gate_min_flow_ratio_pct": float_or_default(
            pc_gates, "min_flow_ratio_pct", defaults.pullback_continuation_gate_min_flow_ratio_pct
        ),
        "pullback_continuation_gate_min_rsi": float_or_default(
            pc_gates, "min_rsi", defaults.pullback_continuation_gate_min_rsi
        ),
        "pullback_continuation_gate_max_rsi": float_or_default(
            pc_gates, "max_rsi", defaults.pullback_continuation_gate_max_rsi
        ),
        "pullback_continuation_gate_min_vwap_discount_pct": float_or_default(
            pc_gates,
            "min_vwap_discount_pct",
            defaults.pullback_continuation_gate_min_vwap_discount_pct,
        ),
        "pullback_continuation_partial_max_failed_gates": int_or_default(
            pc, "partial_max_failed_gates", defaults.pullback_continuation_partial_max_failed_gates
        ),
        "pullback_continuation_family": str_or_default(
            pc, "family", defaults.pullback_continuation_family
        ),
        "pullback_continuation_entry_authority": bool_or_default(
            pc, "entry_authority", defaults.pullback_continuation_entry_authority
        ),
        "pullback_continuation_can_enter_from_phases": phase_names_or_default(
            pc, "can_enter_from_phases", defaults.pullback_continuation_can_enter_from_phases
        ),
    }
