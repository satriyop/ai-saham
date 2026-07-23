"""
Swing setup catalog helpers.

Layer: Application
"""

from __future__ import annotations

from typing import Any

from src.application.use_case.evaluate_swing_setup_use_case import (
    CoiledSpringSetupConfig,
    ForeignBounceSetupConfig,
    PullbackContinuationSetupConfig,
    SmartMoneyConfirmedSetupConfig,
    SwingSetupCatalogConfig,
)


def build_swing_setup_catalog_config(swing_config: Any) -> SwingSetupCatalogConfig:
    """Map loaded swing workflow config into setup-evaluation config."""
    return SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(
            enabled=swing_config.foreign_bounce_enabled,
            gate_min_accum_score=swing_config.gate_min_accum_score,
            gate_min_vwap_discount_pct=swing_config.gate_min_vwap_discount_pct,
            gate_required_trend=swing_config.gate_required_trend,
            gate_min_flow_ratio_pct=swing_config.gate_min_flow_ratio_pct,
            gate_max_rsi=swing_config.gate_max_rsi,
            partial_max_failed_gates=swing_config.partial_max_failed_gates,
            family=swing_config.foreign_bounce_family,
            entry_authority=swing_config.foreign_bounce_entry_authority,
            can_enter_from_phases=swing_config.foreign_bounce_can_enter_from_phases,
        ),
        coiled_spring=CoiledSpringSetupConfig(
            enabled=swing_config.coiled_spring_enabled,
            gate_min_accum_score=swing_config.coiled_spring_gate_min_accum_score,
            gate_max_bb_width_pctile=swing_config.coiled_spring_gate_max_bb_width_pctile,
            gate_min_flow_ratio_pct=swing_config.coiled_spring_gate_min_flow_ratio_pct,
            gate_max_rsi=swing_config.coiled_spring_gate_max_rsi,
            partial_max_failed_gates=swing_config.coiled_spring_partial_max_failed_gates,
            family=swing_config.coiled_spring_family,
            entry_authority=swing_config.coiled_spring_entry_authority,
            can_enter_from_phases=swing_config.coiled_spring_can_enter_from_phases,
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=swing_config.smart_money_confirmed_enabled,
            gate_min_accum_score=swing_config.smart_money_confirmed_gate_min_accum_score,
            gate_min_smart_flow_idr=swing_config.smart_money_confirmed_gate_min_smart_flow_idr,
            gate_min_smart_share_pct=swing_config.smart_money_confirmed_gate_min_smart_share_pct,
            gate_max_noise_share_pct=swing_config.smart_money_confirmed_gate_max_noise_share_pct,
            reject_smart_net_selling=swing_config.smart_money_confirmed_reject_smart_net_selling,
            partial_max_failed_gates=swing_config.smart_money_confirmed_partial_max_failed_gates,
            family=swing_config.smart_money_confirmed_family,
            entry_authority=swing_config.smart_money_confirmed_entry_authority,
            can_enter_from_phases=swing_config.smart_money_confirmed_can_enter_from_phases,
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=swing_config.pullback_continuation_enabled,
            gate_min_accum_score=swing_config.pullback_continuation_gate_min_accum_score,
            gate_required_trend=swing_config.pullback_continuation_gate_required_trend,
            gate_min_flow_ratio_pct=swing_config.pullback_continuation_gate_min_flow_ratio_pct,
            gate_min_rsi=swing_config.pullback_continuation_gate_min_rsi,
            gate_max_rsi=swing_config.pullback_continuation_gate_max_rsi,
            gate_min_vwap_discount_pct=swing_config.pullback_continuation_gate_min_vwap_discount_pct,
            partial_max_failed_gates=swing_config.pullback_continuation_partial_max_failed_gates,
            family=swing_config.pullback_continuation_family,
            entry_authority=swing_config.pullback_continuation_entry_authority,
            can_enter_from_phases=swing_config.pullback_continuation_can_enter_from_phases,
        ),
    )
