"""Typed semantic-contract definition and validation.

Layer: Domain (pure value objects, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
)


_DOTTED_PATH = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*(\.[a-zA-Z][a-zA-Z0-9_-]*)+$")
_LOWERCASE_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")


ACCUMULATION_DISCOVERY_CONTRACT = "accumulation-discovery"

EVIDENCE_CONTRACT_VERSION = "1.2"
SEMANTIC_ENGINE_VERSION = "1.1"

_EXECUTION_LABEL_POLICY_VERSIONS: tuple[tuple[str, str], ...] = (
    ("TACTICAL_3D", "tactical_3d_v1"),
    ("SWING_10D", "swing_10d_v1"),
    ("ACCUM_20D", "accum_20d_v1"),
)

_AUTHORITY_REGISTRATION_NAMES: tuple[str, ...] = (
    "company_quality_context",
    "institutional_flow",
    "market_context",
    "setup_quality",
)

# The Alpha/Trigger evaluation-horizon selector path. It must be declared as
# common material: horizon selection changes which horizon-scoped paths are
# hashed, so the selector value itself must also be part of the hash — else a
# changed horizon could silently repoint identity without changing it.
_EVALUATION_HORIZON_SELECTOR_PATH = "signal_engine.alpha_trigger.default_horizon"

# ---------------------------------------------------------------------------
# Common material config paths — cross-cutting SignalEngine, swing, and
# accumulation-screener inputs consumed before or during canonical assessment.
# ---------------------------------------------------------------------------
_COMMON_MATERIAL_CONFIG_PATHS_BASE: tuple[str, ...] = (
    "accumulation_screener.broker_quality.noise.brokers",
    "accumulation_screener.broker_quality.noise.weight",
    "accumulation_screener.broker_quality.smart_money.brokers",
    "accumulation_screener.broker_quality.smart_money.weight",
    "accumulation_screener.broker_quality.smart_sell_min_share_pct",
    "accumulation_screener.broker_quality.smart_share_threshold_pct",
    "accumulation_screener.broker_quality.tier1.brokers",
    "accumulation_screener.broker_quality.tier1.cluster_min_count",
    "accumulation_screener.broker_quality.tier1.stable_min_count",
    "accumulation_screener.derived_features.bb_history",
    "accumulation_screener.derived_features.bb_period",
    "accumulation_screener.derived_features.insider_lookback_days",
    "accumulation_screener.derived_features.market_vwap_period",
    "accumulation_screener.derived_features.resistance_high_period",
    "accumulation_screener.derived_features.resistance_ma_period",
    "accumulation_screener.derived_features.rsi_period",
    "accumulation_screener.derived_features.trend_sma_period",
    "accumulation_screener.derived_features.trend_threshold_pct",
    "accumulation_screener.evidence.components.bb_squeeze.enabled",
    "accumulation_screener.evidence.components.bb_squeeze.loose_pctile",
    "accumulation_screener.evidence.components.bb_squeeze.tight_pctile",
    "accumulation_screener.evidence.components.bb_squeeze.weight",
    "accumulation_screener.evidence.components.bci.cluster_points",
    "accumulation_screener.evidence.components.bci.enabled",
    "accumulation_screener.evidence.components.bci.stable_points",
    "accumulation_screener.evidence.components.consistency.enabled",
    "accumulation_screener.evidence.components.consistency.weight",
    "accumulation_screener.evidence.components.foreign_flow_ratio.enabled",
    "accumulation_screener.evidence.components.foreign_flow_ratio.saturate_pct",
    "accumulation_screener.evidence.components.foreign_flow_ratio.weight",
    "accumulation_screener.evidence.components.rsi_headroom.enabled",
    "accumulation_screener.evidence.components.rsi_headroom.high",
    "accumulation_screener.evidence.components.rsi_headroom.low",
    "accumulation_screener.evidence.components.rsi_headroom.missing_fraction",
    "accumulation_screener.evidence.components.rsi_headroom.peak",
    "accumulation_screener.evidence.components.rsi_headroom.weight",
    "accumulation_screener.evidence.components.streak.enabled",
    "accumulation_screener.evidence.components.streak.tau_days",
    "accumulation_screener.evidence.components.streak.weight",
    "accumulation_screener.evidence.components.vwap_discount.enabled",
    "accumulation_screener.evidence.components.vwap_discount.saturate_pct",
    "accumulation_screener.evidence.components.vwap_discount.weight",
    "accumulation_screener.evidence.max_score",
    "accumulation_screener.filters.min_foreign_flow_score.enabled",
    "accumulation_screener.filters.min_foreign_flow_score.value",
    "accumulation_screener.filters.min_signal_score.enabled",
    "accumulation_screener.filters.min_signal_score.value",
    "accumulation_screener.screener.min_market_cap_idr",
    "accumulation_screener.sector_breadth.bonus_pts",
    "accumulation_screener.sector_breadth.breadth_threshold",
    "accumulation_screener.sector_breadth.enabled",
    "accumulation_screener.sector_breadth.min_tickers_for_breadth",

    "signal_engine.alpha_trigger.default_horizon",
    "signal_engine.alpha_trigger.enabled",
    "signal_engine.alpha_trigger.group_weights.company_quality_context",
    "signal_engine.alpha_trigger.group_weights.institutional_flow",
    "signal_engine.alpha_trigger.group_weights.market_context",
    "signal_engine.alpha_trigger.group_weights.setup_quality",
    "signal_engine.alpha_trigger.low_weight_cap",
    "signal_engine.classification.moderate_min_score",
    "signal_engine.classification.strong_min_score",
    "signal_engine.decision_policy.regime_policy.NEUTRAL.enter_allowed",
    "signal_engine.decision_policy.regime_policy.NEUTRAL.enter_threshold",
    "signal_engine.decision_policy.regime_policy.NEUTRAL.max_decision",
    "signal_engine.decision_policy.regime_policy.NEUTRAL.min_signal_authority_coverage",
    "signal_engine.decision_policy.regime_policy.NEUTRAL.regime_size_multiplier",
    "signal_engine.decision_policy.regime_policy.NEUTRAL.watch_threshold",
    "signal_engine.decision_policy.regime_policy.RISK_OFF.enter_allowed",
    "signal_engine.decision_policy.regime_policy.RISK_OFF.enter_threshold",
    "signal_engine.decision_policy.regime_policy.RISK_OFF.max_decision",
    "signal_engine.decision_policy.regime_policy.RISK_OFF.min_signal_authority_coverage",
    "signal_engine.decision_policy.regime_policy.RISK_OFF.regime_size_multiplier",
    "signal_engine.decision_policy.regime_policy.RISK_OFF.watch_threshold",
    "signal_engine.decision_policy.regime_policy.RISK_ON.enter_allowed",
    "signal_engine.decision_policy.regime_policy.RISK_ON.enter_threshold",
    "signal_engine.decision_policy.regime_policy.RISK_ON.max_decision",
    "signal_engine.decision_policy.regime_policy.RISK_ON.min_signal_authority_coverage",
    "signal_engine.decision_policy.regime_policy.RISK_ON.regime_size_multiplier",
    "signal_engine.decision_policy.regime_policy.RISK_ON.watch_threshold",
    "signal_engine.decision_policy.regime_policy.VOLATILE.enter_allowed",
    "signal_engine.decision_policy.regime_policy.VOLATILE.enter_threshold",
    "signal_engine.decision_policy.regime_policy.VOLATILE.max_decision",
    "signal_engine.decision_policy.regime_policy.VOLATILE.min_signal_authority_coverage",
    "signal_engine.decision_policy.regime_policy.VOLATILE.regime_size_multiplier",
    "signal_engine.decision_policy.regime_policy.VOLATILE.watch_threshold",
    "signal_engine.decision_policy.setup_regime_actions.allowed.max_decision",
    "signal_engine.decision_policy.setup_regime_actions.allowed_if_flow_confirmation_strong.max_decision",
    "signal_engine.decision_policy.setup_regime_actions.enter_disabled.max_decision",
    "signal_engine.decision_policy.setup_regime_actions.restricted_or_watch_only.max_decision",
    "signal_engine.evidence_groups.flow_confirmation.authority_registration",
    "signal_engine.evidence_groups.flow_confirmation.required_for_authority",
    "signal_engine.evidence_groups.flow_confirmation.weight",
    "signal_engine.evidence_groups.setup_quality.authority_registration",
    "signal_engine.evidence_groups.setup_quality.required_for_authority",
    "signal_engine.evidence_groups.setup_quality.weight",
    "signal_engine.flags.analyst_bearish.buy_ratio_threshold",
    "signal_engine.flags.analyst_bearish.enabled",
    "signal_engine.flags.analyst_bearish.score_penalty",
    "signal_engine.flags.insider_selling.enabled",
    "signal_engine.flags.insider_selling.net_buy_ratio_threshold",
    "signal_engine.flags.insider_selling.score_penalty",
    "signal_engine.flags.valuation_stretched.enabled",
    "signal_engine.flags.valuation_stretched.forward_pe_threshold",
    "signal_engine.flags.valuation_stretched.score_penalty",
    "signal_engine.input_mapping.foreign_flow_score.clamp",
    "signal_engine.input_mapping.foreign_flow_score.max_score",
    "signal_engine.scoring.bandar.default_max_range",
    "signal_engine.scoring.bandar.mandatory_signal_count",
    "signal_engine.scoring.bandar.signal_score_unit",
    "swing_setups.setup_phase.thresholds.breakout_min_close_above_prev_high_pct",
    "swing_setups.setup_phase.thresholds.breakout_reclaim_vwap_min_pct",
    "swing_setups.setup_phase.thresholds.compression_max_bb_width_pctile",
    "swing_setups.setup_phase.thresholds.distribution_min_bandar_score",
    "swing_setups.setup_phase.thresholds.exhaustion_min_price_extension_pct",
    "swing_setups.setup_phase.thresholds.exhaustion_rsi_min",
    "swing_setups.setup_phase.thresholds.failed_breakdown_below_support_pct",
    "swing_setups.setup_phase.thresholds.failed_max_drawdown_from_recent_high_pct",
    "swing_setups.setup_phase.volume_trigger.dry_up_lookback_sessions",
    "swing_setups.setup_phase.volume_trigger.dry_up_max_ratio",
    "swing_setups.setup_phase.volume_trigger.dry_up_reference_sessions",
    "swing_setups.setup_phase.volume_trigger.expansion_min_ratio",
    "swing_setups.setup_phase.volume_trigger.expansion_requires_positive_close",
    "swing_setups.setup_phase.volume_trigger.min_valid_20d_sessions",
    "swing_setups.setup_phase.volume_trigger.require_trusted_volume",
    "swing_setups.setup_phase.volume_trigger.trusted_benchmark_volume_sources",
    "swing_setups.setup_phase.volume_trigger.zero_volume_tolerance",
)

# ---------------------------------------------------------------------------
# Named swing-setup gate paths — common material, not family-scoped.
#
# PrimarySetupFamilyResolver._from_screen_evidence() evaluates every entry in
# AVAILABLE_SWING_SETUPS (foreign-bounce, coiled-spring, smart-money-confirmed,
# pullback-continuation) regardless of which family ends up primary. The
# resulting matched_setup_families is persisted even when a different (or no)
# primary family is selected, so every named setup's gate config is a common
# family-resolution input, not scoped to the family it happens to map to.
#
# entry_authority and can_enter_from_phases are deliberately excluded:
# _from_screen_evidence() only reads SetupEvaluation.match and .family, both
# computed purely from gate pass/fail logic in
# EvaluateSwingSetupUseCase._evaluation(); entry_authority and
# can_enter_from_phases populate separate output-only fields that this
# resolution path never consumes, so they cannot alter the
# accumulation-discovery result.
# ---------------------------------------------------------------------------
_FOREIGN_BOUNCE_SETUP_PATHS: tuple[str, ...] = (
    "swing_setups.setups.foreign-bounce.enabled",
    "swing_setups.setups.foreign-bounce.family",
    "swing_setups.setups.foreign-bounce.gates.max_rsi",
    "swing_setups.setups.foreign-bounce.gates.min_flow_ratio_pct",
    "swing_setups.setups.foreign-bounce.gates.min_foreign_flow_score",
    "swing_setups.setups.foreign-bounce.gates.min_vwap_discount_pct",
    "swing_setups.setups.foreign-bounce.gates.required_trend",
    "swing_setups.setups.foreign-bounce.partial_max_failed_gates",
)

_COILED_SPRING_SETUP_PATHS: tuple[str, ...] = (
    "swing_setups.setups.coiled-spring.enabled",
    "swing_setups.setups.coiled-spring.family",
    "swing_setups.setups.coiled-spring.gates.max_bb_width_pctile",
    "swing_setups.setups.coiled-spring.gates.max_rsi",
    "swing_setups.setups.coiled-spring.gates.min_flow_ratio_pct",
    "swing_setups.setups.coiled-spring.gates.min_foreign_flow_score",
    "swing_setups.setups.coiled-spring.partial_max_failed_gates",
)

_SMART_MONEY_CONFIRMED_SETUP_PATHS: tuple[str, ...] = (
    "swing_setups.setups.smart-money-confirmed.enabled",
    "swing_setups.setups.smart-money-confirmed.family",
    "swing_setups.setups.smart-money-confirmed.gates.max_noise_share_pct",
    "swing_setups.setups.smart-money-confirmed.gates.min_foreign_flow_score",
    "swing_setups.setups.smart-money-confirmed.gates.min_smart_flow_idr",
    "swing_setups.setups.smart-money-confirmed.gates.min_smart_share_pct",
    "swing_setups.setups.smart-money-confirmed.gates.reject_smart_net_selling",
    "swing_setups.setups.smart-money-confirmed.partial_max_failed_gates",
)

_PULLBACK_CONTINUATION_SETUP_PATHS: tuple[str, ...] = (
    "swing_setups.setups.pullback-continuation.enabled",
    "swing_setups.setups.pullback-continuation.family",
    "swing_setups.setups.pullback-continuation.gates.max_rsi",
    "swing_setups.setups.pullback-continuation.gates.min_flow_ratio_pct",
    "swing_setups.setups.pullback-continuation.gates.min_foreign_flow_score",
    "swing_setups.setups.pullback-continuation.gates.min_rsi",
    "swing_setups.setups.pullback-continuation.gates.min_vwap_discount_pct",
    "swing_setups.setups.pullback-continuation.gates.required_trend",
    "swing_setups.setups.pullback-continuation.partial_max_failed_gates",
)

_SETUP_FAMILY_RESOLUTION_PATHS: tuple[str, ...] = tuple(sorted(set(
    _FOREIGN_BOUNCE_SETUP_PATHS
    + _COILED_SPRING_SETUP_PATHS
    + _SMART_MONEY_CONFIRMED_SETUP_PATHS
    + _PULLBACK_CONTINUATION_SETUP_PATHS
)))

_FOREIGN_BOUNCE_DECISION_POLICY_PATHS: tuple[str, ...] = (
    "signal_engine.decision_policy.setup_regime_policy.foreign_bounce.NEUTRAL",
    "signal_engine.decision_policy.setup_regime_policy.foreign_bounce.RISK_OFF",
    "signal_engine.decision_policy.setup_regime_policy.foreign_bounce.RISK_ON",
    "signal_engine.decision_policy.setup_regime_policy.foreign_bounce.VOLATILE",
)


# ---------------------------------------------------------------------------
# Persisted evidence-producer material config — every config root whose
# active values feed evidence persisted in the canonical observation
# fingerprint (institutional accumulation, ticker profile, sector context,
# company quality context, market context), even while that evidence remains
# DIAGNOSTIC. These are common material, not family-scoped.
# ---------------------------------------------------------------------------
_INSTITUTIONAL_ACCUMULATION_PATHS: tuple[str, ...] = (
    "institutional_accumulation.broker_classification.foreign_broker_codes",
    "institutional_accumulation.domestic_bandar_track_components.accumulation_session_ratio",
    "institutional_accumulation.domestic_bandar_track_components.bandar_broad_or_accumulation_score",
    "institutional_accumulation.domestic_bandar_track_components.broker_consistency",
    "institutional_accumulation.domestic_bandar_track_components.broker_hhi_divergence",
    "institutional_accumulation.domestic_bandar_track_components.broker_reversal",
    "institutional_accumulation.domestic_bandar_track_components.domestic_buy_vwap_distance",
    "institutional_accumulation.foreign_institutional_track_components.cnfb_price_divergence",
    "institutional_accumulation.foreign_institutional_track_components.foreign_concentration_cr4_cr8",
    "institutional_accumulation.foreign_institutional_track_components.foreign_participation",
    "institutional_accumulation.foreign_institutional_track_components.foreign_vwap_distance",
    "institutional_accumulation.min_valid_sessions.broker_consistency",
    "institutional_accumulation.min_valid_sessions.cnfb_20d",
    "institutional_accumulation.min_valid_sessions.cnfb_30d",
    "institutional_accumulation.min_valid_sessions.cnfb_3d",
    "institutional_accumulation.min_valid_sessions.vwap_20d",
    "institutional_accumulation.track_weights.counterparty_transfer",
    "institutional_accumulation.track_weights.domestic_bandar_track",
    "institutional_accumulation.track_weights.foreign_institutional_track",
    "institutional_accumulation.windows.broker_consistency_days",
    "institutional_accumulation.windows.cnfb_bearish_distribution",
    "institutional_accumulation.windows.cnfb_bullish_accumulation",
    "institutional_accumulation.windows.counterparty_window_days",
    "institutional_accumulation.windows.domestic_vwap_days",
    "institutional_accumulation.windows.foreign_vwap_days",
)

_TICKER_PROFILE_PATHS: tuple[str, ...] = (
    "ticker_profile.conservative_fallback_confidence",
    # epoch_cadence excluded: TickerProfileConfig.from_mapping() does not
    # consume it, and TickerProfileClassifier derives the epoch directly from
    # snapshot_date, never from a configured cadence value.
    "ticker_profile.evidence_status",
    "ticker_profile.exposure_weights.domestic_bandar.broker_concentration",
    "ticker_profile.exposure_weights.domestic_bandar.foreign_flow_inverse",
    "ticker_profile.exposure_weights.domestic_bandar.liquidity",
    "ticker_profile.exposure_weights.foreign_institutional.broker_concentration_inverse",
    "ticker_profile.exposure_weights.foreign_institutional.foreign_flow",
    "ticker_profile.exposure_weights.foreign_institutional.index_membership",
    "ticker_profile.exposure_weights.foreign_institutional.liquidity",
    "ticker_profile.exposure_weights.retail_speculative.liquidity_inverse",
    "ticker_profile.exposure_weights.retail_speculative.market_cap_speculative",
    "ticker_profile.exposure_weights.retail_speculative.volatility",
    "ticker_profile.index_membership_scores.idx30",
    "ticker_profile.index_membership_scores.idx80",
    "ticker_profile.index_membership_scores.jii",
    "ticker_profile.index_membership_scores.lq45",
    "ticker_profile.index_membership_scores.mbx",
    "ticker_profile.liquidity_thresholds.high_daily_value_idr",
    "ticker_profile.liquidity_thresholds.low_daily_value_idr",
    "ticker_profile.market_cap_thresholds_idr.large",
    "ticker_profile.market_cap_thresholds_idr.mid",
    "ticker_profile.market_cap_thresholds_idr.small",
    "ticker_profile.profile_window_days",
    "ticker_profile.sparse_history_threshold",
    "ticker_profile.volatility_thresholds.high_atr_pct",
    "ticker_profile.volatility_thresholds.low_atr_pct",
)

_SECTOR_CONTEXT_PATHS: tuple[str, ...] = (
    "sector_context.lookback_sessions",
    "sector_context.max_peer_count",
    "sector_context.min_peer_count",
    "sector_context.min_valid_sessions_per_peer",
    "sector_context.sector_regime_thresholds.bearish.breadth_max",
    "sector_context.sector_regime_thresholds.bearish.sector_vs_ihsg_max",
    "sector_context.sector_regime_thresholds.bullish.breadth_min",
    "sector_context.sector_regime_thresholds.bullish.sector_vs_ihsg_min",
)

_COMPANY_QUALITY_CONTEXT_PATHS: tuple[str, ...] = (
    "company_quality_context.axis_weights.analyst",
    "company_quality_context.axis_weights.insider",
    "company_quality_context.axis_weights.valuation",
    "company_quality_context.scored_axis_count",
    "company_quality_context.seasonality_weight",
)

_MARKET_CONTEXT_ENGINE_PATHS: tuple[str, ...] = (
    "market_context_engine.factors.commodity_composite.components",
    "market_context_engine.factors.commodity_composite.enabled",
    "market_context_engine.factors.commodity_composite.thresholds.drawdown_risk_off_pct",
    "market_context_engine.factors.commodity_composite.thresholds.lookback_days",
    "market_context_engine.factors.commodity_composite.thresholds.rally_risk_on_pct",
    "market_context_engine.factors.commodity_composite.weight",
    "market_context_engine.factors.eido.enabled",
    "market_context_engine.factors.eido.thresholds.discount_pct",
    "market_context_engine.factors.eido.thresholds.lookback_days",
    "market_context_engine.factors.eido.thresholds.premium_pct",
    "market_context_engine.factors.eido.ticker",
    "market_context_engine.factors.eido.weight",
    "market_context_engine.factors.foreign_flow.enabled",
    "market_context_engine.factors.foreign_flow.thresholds.bearish_diff_ratio",
    "market_context_engine.factors.foreign_flow.thresholds.bullish_diff_ratio",
    "market_context_engine.factors.foreign_flow.thresholds.lookback_days",
    "market_context_engine.factors.foreign_flow.thresholds.reference_days",
    "market_context_engine.factors.foreign_flow.weight",
    "market_context_engine.factors.idx_breadth.enabled",
    "market_context_engine.factors.idx_breadth.thresholds.above_sma_period",
    "market_context_engine.factors.idx_breadth.thresholds.bearish_pct",
    "market_context_engine.factors.idx_breadth.thresholds.bullish_pct",
    "market_context_engine.factors.idx_breadth.weight",
    "market_context_engine.factors.idx_trend.benchmark_ticker",
    "market_context_engine.factors.idx_trend.enabled",
    "market_context_engine.factors.idx_trend.thresholds.above_pct_strong",
    "market_context_engine.factors.idx_trend.thresholds.below_pct_strong",
    "market_context_engine.factors.idx_trend.thresholds.fast_sma_adjustment",
    "market_context_engine.factors.idx_trend.thresholds.sma_fast",
    "market_context_engine.factors.idx_trend.thresholds.sma_slow",
    "market_context_engine.factors.idx_trend.weight",
    "market_context_engine.factors.usd_idr.enabled",
    "market_context_engine.factors.usd_idr.thresholds.lookback_days",
    "market_context_engine.factors.usd_idr.thresholds.strengthen_pct",
    "market_context_engine.factors.usd_idr.thresholds.weaken_pct",
    "market_context_engine.factors.usd_idr.ticker",
    "market_context_engine.factors.usd_idr.weight",
    "market_context_engine.factors.vix.enabled",
    "market_context_engine.factors.vix.score_anchors.elevated",
    "market_context_engine.factors.vix.score_anchors.high",
    "market_context_engine.factors.vix.score_anchors.low",
    "market_context_engine.factors.vix.score_anchors.risk_off",
    "market_context_engine.factors.vix.score_anchors.very_low",
    "market_context_engine.factors.vix.thresholds.elevated",
    "market_context_engine.factors.vix.thresholds.high",
    "market_context_engine.factors.vix.thresholds.low",
    "market_context_engine.factors.vix.thresholds.very_low",
    "market_context_engine.factors.vix.ticker",
    "market_context_engine.factors.vix.weight",
    "market_context_engine.fetch.global_context_end_tolerance_days",
    "market_context_engine.regime_effects.NEUTRAL.gate_tightening",
    "market_context_engine.regime_effects.NEUTRAL.signal_multiplier",
    "market_context_engine.regime_effects.RISK_OFF.gate_tightening",
    "market_context_engine.regime_effects.RISK_OFF.signal_multiplier",
    "market_context_engine.regime_effects.RISK_ON.gate_tightening",
    "market_context_engine.regime_effects.RISK_ON.signal_multiplier",
    "market_context_engine.regime_effects.VOLATILE.gate_tightening",
    "market_context_engine.regime_effects.VOLATILE.signal_multiplier",
    "market_context_engine.regime_thresholds.risk_off_max_score",
    "market_context_engine.regime_thresholds.risk_on_min_score",
    "market_context_engine.regime_thresholds.volatile_vix_override",
    "market_context_engine.scoring.coverage_warning_unavailable_ratio",
    "market_context_engine.scoring.labels.favorable_min_score",
    "market_context_engine.scoring.labels.neutral_min_score",
    "market_context_engine.scoring.neutral_score",
    "market_context_engine.scoring.stale_business_day_gap",
)

_COMMON_MATERIAL_CONFIG_PATHS: tuple[str, ...] = tuple(sorted(set(
    _COMMON_MATERIAL_CONFIG_PATHS_BASE
    + _SETUP_FAMILY_RESOLUTION_PATHS
    + _INSTITUTIONAL_ACCUMULATION_PATHS
    + _TICKER_PROFILE_PATHS
    + _SECTOR_CONTEXT_PATHS
    + _COMPANY_QUALITY_CONTEXT_PATHS
    + _MARKET_CONTEXT_ENGINE_PATHS
)))


# ---------------------------------------------------------------------------
# Per-setup-family material config paths — post-selection policy only.
# Named-setup gate config that decides matched_setup_families now lives in
# _SETUP_FAMILY_RESOLUTION_PATHS (common); a family group here contains only
# the policy applied *after* a family is selected.
# ---------------------------------------------------------------------------
_MATERIAL_CONFIG_PATHS_BY_SETUP_FAMILY: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "accumulation",
        (
            "swing_setups.setup_phase.requirements.accumulation.enter_phases",
            "swing_setups.setup_phase.requirements.accumulation.required_sequence",
        ),
    ),
    (
        "breakout",
        (
            "swing_setups.setup_phase.requirements.breakout.enter_phases",
            "swing_setups.setup_phase.requirements.breakout.required_sequence",
        ),
    ),
    (
        "foreign_bounce",
        tuple(sorted(set(
            (
                "swing_setups.setup_phase.requirements.accumulation.enter_phases",
                "swing_setups.setup_phase.requirements.accumulation.required_sequence",
            )
            + _FOREIGN_BOUNCE_DECISION_POLICY_PATHS
        ))),
    ),
    (
        "mean_reversion",
        (),
    ),
    (
        "pullback",
        (
            "swing_setups.setup_phase.requirements.pullback.enter_phases",
            "swing_setups.setup_phase.requirements.pullback.required_sequence",
            "swing_setups.setup_phase.requirements.pullback.requires_reclaim_or_pivot",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Material config paths by evaluated Alpha/Trigger horizon — only the
# horizon actually evaluated (signal_engine.alpha_trigger.default_horizon,
# since accumulation-discovery passes no horizon override) is selected.
# ---------------------------------------------------------------------------
_MATERIAL_CONFIG_PATHS_BY_EVALUATION_HORIZON: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ACCUM_20D",
        (
            "signal_engine.alpha_trigger.horizon_alpha_weights.ACCUM_20D",
            "signal_engine.alpha_trigger.route_fractions.ACCUM_20D.company_quality_context.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.ACCUM_20D.institutional_flow.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.ACCUM_20D.market_context.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.ACCUM_20D.setup_quality.alpha_fraction",
        ),
    ),
    (
        "SWING_10D",
        (
            "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D",
            "signal_engine.alpha_trigger.route_fractions.SWING_10D.company_quality_context.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.SWING_10D.institutional_flow.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.SWING_10D.market_context.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.SWING_10D.setup_quality.alpha_fraction",
        ),
    ),
    (
        "TACTICAL_3D",
        (
            "signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D",
            "signal_engine.alpha_trigger.route_fractions.TACTICAL_3D.company_quality_context.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.TACTICAL_3D.institutional_flow.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.TACTICAL_3D.market_context.alpha_fraction",
            "signal_engine.alpha_trigger.route_fractions.TACTICAL_3D.setup_quality.alpha_fraction",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Unordered-collection normalization metadata — these config values are sets
# of broker codes / phase-membership / source names whose order carries no
# meaning. required_sequence is deliberately excluded from both: its order is
# semantic (it is a state machine sequence, not a set).
# ---------------------------------------------------------------------------
_UNORDERED_UPPER_STRING_CONFIG_PATHS: tuple[str, ...] = tuple(sorted((
    "accumulation_screener.broker_quality.noise.brokers",
    "accumulation_screener.broker_quality.smart_money.brokers",
    "accumulation_screener.broker_quality.tier1.brokers",
    "institutional_accumulation.broker_classification.foreign_broker_codes",
    "swing_setups.setup_phase.requirements.accumulation.enter_phases",
    "swing_setups.setup_phase.requirements.breakout.enter_phases",
    "swing_setups.setup_phase.requirements.pullback.enter_phases",
)))

_UNORDERED_LOWER_STRING_CONFIG_PATHS: tuple[str, ...] = (
    "swing_setups.setup_phase.volume_trigger.trusted_benchmark_volume_sources",
)

# ---------------------------------------------------------------------------
# Unordered-integer-window normalization metadata — these are windows of
# session counts modeled as unordered multisets: reordering is non-semantic,
# but duplicate multiplicity is preserved because some consumers iterate and
# average every configured occurrence. Scalar day counts (foreign_vwap_days,
# domestic_vwap_days, counterparty_window_days) and required_sequence are
# deliberately excluded — required_sequence remains ordered, and the others
# are not unordered multisets.
# ---------------------------------------------------------------------------
_UNORDERED_INTEGER_CONFIG_PATHS: tuple[str, ...] = tuple(sorted((
    "institutional_accumulation.windows.broker_consistency_days",
    "institutional_accumulation.windows.cnfb_bearish_distribution",
    "institutional_accumulation.windows.cnfb_bullish_accumulation",
)))

# ---------------------------------------------------------------------------
# Commodity-component normalization metadata — specialized to the current
# commodity_composite.components parser contract (exactly one cpo + one coal
# leg, classified by "KO" substring in the ticker), not a generic list-of-
# object sorter.
# ---------------------------------------------------------------------------
_COMMODITY_COMPONENT_CONFIG_PATHS: tuple[str, ...] = (
    "market_context_engine.factors.commodity_composite.components",
)


def _fail(value: object, field: str, msg: str) -> None:
    raise ValueError(f"{field}: {msg}, got {value!r}")


def _require_dotted_paths(value: tuple[str, ...], field: str) -> None:
    if not isinstance(value, tuple):
        _fail(value, field, "must be a tuple")
    if not value:
        _fail(value, field, "must be a non-empty tuple")
    for i, p in enumerate(value):
        if not isinstance(p, str) or not _DOTTED_PATH.match(p):
            _fail(value, f"{field}[{i}]", f"invalid dotted path {p!r}")
    if sorted(value) != list(value):
        _fail(value, field, "paths must be sorted")
    seen = set()
    for p in value:
        if p in seen:
            _fail(value, field, f"duplicate path {p!r}")
        seen.add(p)


def _require_non_empty_trimmed(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(value, field, "must be a non-empty trimmed string")
    if value != value.strip():
        _fail(value, field, "must not have surrounding whitespace")


def _require_lowercase_snake(value: str, field: str) -> None:
    _require_non_empty_trimmed(value, field)
    if not _LOWERCASE_SNAKE.match(value):
        _fail(value, field, "must be lowercase snake_case")


def _require_positive_int(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(value, field, f"must be a positive int, not {type(value).__name__}")
    if value < 1:
        _fail(value, field, f"must be positive, got {value}")


def _require_sorted_strings(value: tuple[str, ...], field: str) -> None:
    if not isinstance(value, tuple):
        _fail(value, field, "must be a tuple")
    if not value:
        _fail(value, field, "must be non-empty")
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _fail(value, f"{field}[{i}]", "must be a non-empty trimmed string")
    if sorted(value) != list(value):
        _fail(value, field, "must be sorted")
    seen = set()
    for item in value:
        if item in seen:
            _fail(value, field, f"duplicate item {item!r}")
        seen.add(item)


def _require_execution_label_policy_versions(
    value: tuple[tuple[str, str], ...],
    field: str,
) -> None:
    if not isinstance(value, tuple):
        _fail(value, field, "must be a tuple")
    if not value:
        _fail(value, field, "must be non-empty")
    seen = set()
    for i, (horizon, version) in enumerate(value):
        if not isinstance(horizon, str) or not isinstance(version, str):
            _fail(
                value,
                f"{field}[{i}]",
                "each pair must be (str, str)",
            )
        if not horizon.strip():
            _fail(value, f"{field}[{i}][0]", "horizon must be non-empty")
        if not version.strip():
            _fail(value, f"{field}[{i}][1]", "version must be non-empty")
        if horizon in seen:
            _fail(value, f"{field}[{i}]", f"duplicate horizon {horizon!r}")
        seen.add(horizon)


def _require_per_family_paths(
    value: tuple[tuple[str, tuple[str, ...]], ...],
    field: str,
) -> None:
    if not isinstance(value, tuple):
        _fail(value, field, "must be a tuple")
    seen_families = set()
    for i, (family, paths) in enumerate(value):
        prefix = f"{field}[{i}]"
        if not isinstance(family, str) or not _LOWERCASE_SNAKE.match(family):
            _fail(value, f"{prefix}[0]", f"invalid family name {family!r}")
        if family in seen_families:
            _fail(value, f"{prefix}[0]", f"duplicate family {family!r}")
        seen_families.add(family)
        if not isinstance(paths, tuple):
            _fail(value, f"{prefix}[1]", "paths must be a tuple")
        if paths:
            _require_dotted_paths(paths, f"{prefix}[1]")


def _require_evaluation_horizon_selector_present(
    common_paths: tuple[str, ...],
    field: str,
) -> None:
    if _EVALUATION_HORIZON_SELECTOR_PATH not in common_paths:
        _fail(
            common_paths,
            field,
            f"must include evaluation-horizon selector path "
            f"{_EVALUATION_HORIZON_SELECTOR_PATH!r}",
        )


def _require_material_config_paths_by_evaluation_horizon(
    value: tuple[tuple[str, tuple[str, ...]], ...],
    field: str,
) -> None:
    if not isinstance(value, tuple):
        _fail(value, field, "must be a tuple")
    if not value:
        _fail(value, field, "must be a non-empty tuple")
    horizons: list[str] = []
    for i, (horizon, paths) in enumerate(value):
        prefix = f"{field}[{i}]"
        if not isinstance(horizon, str) or not horizon.strip():
            _fail(value, f"{prefix}[0]", f"invalid evaluation horizon {horizon!r}")
        if horizon != horizon.strip():
            _fail(value, f"{prefix}[0]", "horizon must not have surrounding whitespace")
        horizons.append(horizon)
        if not isinstance(paths, tuple):
            _fail(value, f"{prefix}[1]", "paths must be a tuple")
        _require_dotted_paths(paths, f"{prefix}[1]")
    if sorted(horizons) != horizons:
        _fail(value, field, "horizon groups must be sorted")
    seen_horizons = set()
    for horizon in horizons:
        if horizon in seen_horizons:
            _fail(value, field, f"duplicate horizon {horizon!r}")
        seen_horizons.add(horizon)


def _require_optional_sorted_dotted_paths(
    value: tuple[str, ...],
    field: str,
) -> None:
    """Like _require_dotted_paths, but an empty tuple is allowed."""
    if not isinstance(value, tuple):
        _fail(value, field, "must be a tuple")
    for i, p in enumerate(value):
        if not isinstance(p, str) or not _DOTTED_PATH.match(p):
            _fail(value, f"{field}[{i}]", f"invalid dotted path {p!r}")
    if sorted(value) != list(value):
        _fail(value, field, "paths must be sorted")
    seen = set()
    for p in value:
        if p in seen:
            _fail(value, field, f"duplicate path {p!r}")
        seen.add(p)


def _require_no_normalization_overlap(
    named_collections: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    """Pairwise-check every normalization collection for shared paths.

    A path may declare at most one normalization behavior; belonging to two
    collections (e.g. both unordered-upper-string and unordered-integer)
    would make canonicalization ambiguous.
    """
    for i, (name_i, paths_i) in enumerate(named_collections):
        for name_j, paths_j in named_collections[i + 1:]:
            overlap = set(paths_i) & set(paths_j)
            if overlap:
                _fail(
                    sorted(overlap),
                    name_i,
                    f"{name_i} and {name_j} must not overlap",
                )


def _require_normalization_paths_are_declared_material(
    normalization_paths: tuple[str, ...],
    all_declared_material_paths: set[str],
    field: str,
) -> None:
    for path in normalization_paths:
        if path not in all_declared_material_paths:
            _fail(
                path,
                field,
                f"normalization path {path!r} is not declared in common, "
                "family, or horizon material paths",
            )


# ---------------------------------------------------------------------------
# SemanticContractDefinition — typed contract definition with fail-closed
# validation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticContractDefinition:
    """Typed definition for one semantic observation/label contract."""

    observation_contract: str
    evidence_contract_version: str
    semantic_engine_version: str
    observation_schema_version: int
    label_schema_version: int
    execution_label_policy_versions: tuple[tuple[str, str], ...]
    common_material_config_paths: tuple[str, ...]
    material_config_paths_by_setup_family: tuple[tuple[str, tuple[str, ...]], ...]
    material_config_paths_by_evaluation_horizon: tuple[tuple[str, tuple[str, ...]], ...]
    authority_registration_names: tuple[str, ...]
    unordered_upper_string_config_paths: tuple[str, ...] = ()
    unordered_lower_string_config_paths: tuple[str, ...] = ()
    unordered_integer_config_paths: tuple[str, ...] = ()
    commodity_component_config_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_trimmed(
            self.observation_contract, "observation_contract",
        )
        _require_non_empty_trimmed(
            self.evidence_contract_version, "evidence_contract_version",
        )
        _require_non_empty_trimmed(
            self.semantic_engine_version, "semantic_engine_version",
        )
        _require_positive_int(
            self.observation_schema_version, "observation_schema_version",
        )
        _require_positive_int(
            self.label_schema_version, "label_schema_version",
        )
        _require_execution_label_policy_versions(
            self.execution_label_policy_versions,
            "execution_label_policy_versions",
        )
        _require_dotted_paths(
            self.common_material_config_paths,
            "common_material_config_paths",
        )
        _require_evaluation_horizon_selector_present(
            self.common_material_config_paths,
            "common_material_config_paths",
        )
        _require_per_family_paths(
            self.material_config_paths_by_setup_family,
            "material_config_paths_by_setup_family",
        )
        _require_material_config_paths_by_evaluation_horizon(
            self.material_config_paths_by_evaluation_horizon,
            "material_config_paths_by_evaluation_horizon",
        )
        _require_sorted_strings(
            self.authority_registration_names, "authority_registration_names",
        )
        _require_optional_sorted_dotted_paths(
            self.unordered_upper_string_config_paths,
            "unordered_upper_string_config_paths",
        )
        _require_optional_sorted_dotted_paths(
            self.unordered_lower_string_config_paths,
            "unordered_lower_string_config_paths",
        )
        _require_optional_sorted_dotted_paths(
            self.unordered_integer_config_paths,
            "unordered_integer_config_paths",
        )
        _require_optional_sorted_dotted_paths(
            self.commodity_component_config_paths,
            "commodity_component_config_paths",
        )
        _require_no_normalization_overlap((
            ("unordered_upper_string_config_paths", self.unordered_upper_string_config_paths),
            ("unordered_lower_string_config_paths", self.unordered_lower_string_config_paths),
            ("unordered_integer_config_paths", self.unordered_integer_config_paths),
            ("commodity_component_config_paths", self.commodity_component_config_paths),
        ))
        all_declared_material_paths: set[str] = set(self.common_material_config_paths)
        for _family, family_paths in self.material_config_paths_by_setup_family:
            all_declared_material_paths |= set(family_paths)
        for _horizon, horizon_paths in self.material_config_paths_by_evaluation_horizon:
            all_declared_material_paths |= set(horizon_paths)
        _require_normalization_paths_are_declared_material(
            self.unordered_upper_string_config_paths,
            all_declared_material_paths,
            "unordered_upper_string_config_paths",
        )
        _require_normalization_paths_are_declared_material(
            self.unordered_lower_string_config_paths,
            all_declared_material_paths,
            "unordered_lower_string_config_paths",
        )
        _require_normalization_paths_are_declared_material(
            self.unordered_integer_config_paths,
            all_declared_material_paths,
            "unordered_integer_config_paths",
        )
        _require_normalization_paths_are_declared_material(
            self.commodity_component_config_paths,
            all_declared_material_paths,
            "commodity_component_config_paths",
        )

    def material_paths_for(
        self,
        *,
        setup_family: str | None,
        evaluation_horizon: str,
    ) -> tuple[str, ...]:
        """Return common + evaluation-horizon + (optional) setup-family paths.

        Only the Alpha/Trigger horizon actually evaluated is selected; other
        declared horizons' paths are excluded so they cannot fragment
        compatibility identity.
        """
        paths = list(self.common_material_config_paths)

        horizon_found = False
        for horizon, horizon_paths in self.material_config_paths_by_evaluation_horizon:
            if horizon == evaluation_horizon:
                paths.extend(horizon_paths)
                horizon_found = True
                break
        if not horizon_found:
            raise ValueError(
                f"unknown evaluation_horizon {evaluation_horizon!r}; "
                f"known: {[h for h, _ in self.material_config_paths_by_evaluation_horizon]}"
            )

        if setup_family is not None:
            family_found = False
            for family, family_paths in self.material_config_paths_by_setup_family:
                if family == setup_family:
                    paths.extend(family_paths)
                    family_found = True
                    break
            if not family_found:
                raise ValueError(
                    f"unknown setup_family {setup_family!r}; "
                    f"known: {[f for f, _ in self.material_config_paths_by_setup_family]}"
                )

        return tuple(sorted(set(paths)))

    def label_policy_version(self, horizon: str) -> str:
        for h, version in self.execution_label_policy_versions:
            if h == horizon:
                return version
        raise ValueError(
            f"unknown horizon {horizon!r}; "
            f"known: {[h for h, _ in self.execution_label_policy_versions]}"
        )


# ---------------------------------------------------------------------------
# Known contract instance
# ---------------------------------------------------------------------------

ACCUMULATION_DISCOVERY = SemanticContractDefinition(
    observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
    evidence_contract_version=EVIDENCE_CONTRACT_VERSION,
    semantic_engine_version=SEMANTIC_ENGINE_VERSION,
    observation_schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    label_schema_version=SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
    execution_label_policy_versions=_EXECUTION_LABEL_POLICY_VERSIONS,
    common_material_config_paths=_COMMON_MATERIAL_CONFIG_PATHS,
    material_config_paths_by_setup_family=_MATERIAL_CONFIG_PATHS_BY_SETUP_FAMILY,
    material_config_paths_by_evaluation_horizon=_MATERIAL_CONFIG_PATHS_BY_EVALUATION_HORIZON,
    authority_registration_names=_AUTHORITY_REGISTRATION_NAMES,
    unordered_upper_string_config_paths=_UNORDERED_UPPER_STRING_CONFIG_PATHS,
    unordered_lower_string_config_paths=_UNORDERED_LOWER_STRING_CONFIG_PATHS,
    unordered_integer_config_paths=_UNORDERED_INTEGER_CONFIG_PATHS,
    commodity_component_config_paths=_COMMODITY_COMPONENT_CONFIG_PATHS,
)
