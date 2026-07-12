"""Serialization and parsing logic for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import (
    _optional_bool,
    _optional_float,
    _optional_int,
)

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def signal_observation_fingerprint_to_dict(
    fingerprint: "SignalObservationFingerprint",
) -> dict[str, Any]:
    """Serialize a SignalObservationFingerprint to a flat dictionary."""
    data = {}

    # Setup fields
    data.update(_serialize_setup_fields(fingerprint))

    # Strategy fields
    data.update(_serialize_strategy_fields(fingerprint))

    # Flow fields
    data.update(_serialize_flow_fields(fingerprint))

    # Regime fields
    data.update(_serialize_regime_fields(fingerprint))

    # Institutional accumulation fields
    data.update(_serialize_institutional_accumulation_fields(fingerprint))

    # Ticker profile fields
    data.update(_serialize_ticker_profile_fields(fingerprint))

    # Sector context fields
    data.update(_serialize_sector_context_fields(fingerprint))

    # Company quality fields
    data.update(_serialize_company_quality_fields(fingerprint))

    # Alpha/trigger fields
    data.update(_serialize_alpha_trigger_fields(fingerprint))

    # Volatility fields
    data.update(_serialize_volatility_fields(fingerprint))

    return data


def signal_observation_fingerprint_from_dict(
    cls, data: dict[str, Any]
) -> Any:
    """Reconstruct a SignalObservationFingerprint from a flat dictionary."""
    # Setup fields
    setup_kwargs = _parse_setup_fields(data)

    # Strategy fields
    strategy_kwargs = _parse_strategy_fields(data)

    # Flow fields
    flow_kwargs = _parse_flow_fields(data)

    # Regime fields
    regime_kwargs = _parse_regime_fields(data)

    # Institutional accumulation fields
    ia_kwargs = _parse_institutional_accumulation_fields(data)

    # Ticker profile fields
    tp_kwargs = _parse_ticker_profile_fields(data)

    # Sector context fields
    sc_kwargs = _parse_sector_context_fields(data)

    # Company quality fields
    cq_kwargs = _parse_company_quality_fields(data)

    # Alpha/trigger fields
    alpha_trigger_kwargs = _parse_alpha_trigger_fields(data)

    # Volatility fields
    volatility_kwargs = _parse_volatility_fields(data)

    # Combine all arguments
    kwargs = {}
    kwargs.update(setup_kwargs)
    kwargs.update(strategy_kwargs)
    kwargs.update(flow_kwargs)
    kwargs.update(regime_kwargs)
    kwargs.update(ia_kwargs)
    kwargs.update(tp_kwargs)
    kwargs.update(sc_kwargs)
    kwargs.update(cq_kwargs)
    kwargs.update(alpha_trigger_kwargs)
    kwargs.update(volatility_kwargs)

    return cls(**kwargs)


# --- SETUP FIELDS ---

def _serialize_setup_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "setup_family": fp.setup_family,
        "matched_setup_families": list(fp.matched_setup_families),
        "primary_setup_family": fp.primary_setup_family,
        "setup_family_source": fp.setup_family_source,
        "setup_family_rationale": list(fp.setup_family_rationale),
        "setup_name": fp.setup_name,
        "setup_phase": fp.setup_phase,
        "setup_phase_previous": fp.setup_phase_previous,
        "phase_sequence_valid": fp.phase_sequence_valid,
        "phase_age_sessions": fp.phase_age_sessions,
        "phase_strength": fp.phase_strength,
        "phase_reasons": list(fp.phase_reasons),
        "phase_history": [dict(entry) for entry in fp.phase_history],
        "phase_coverage_score": fp.phase_coverage_score,
        "phase_conviction_score": fp.phase_conviction_score,
    }


def _parse_setup_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "setup_family": data.get("setup_family"),
        "matched_setup_families": tuple(
            str(v) for v in data.get("matched_setup_families") or ()
        ),
        "primary_setup_family": data.get("primary_setup_family"),
        "setup_family_source": data.get("setup_family_source"),
        "setup_family_rationale": tuple(
            str(v) for v in data.get("setup_family_rationale") or ()
        ),
        "setup_name": data.get("setup_name"),
        "setup_phase": data.get("setup_phase") or data.get("setup_phase_current"),
        "setup_phase_previous": data.get("setup_phase_previous"),
        "phase_sequence_valid": _optional_bool(data.get("phase_sequence_valid")),
        "phase_age_sessions": _optional_int(data.get("phase_age_sessions")),
        "phase_strength": _optional_float(data.get("phase_strength")),
        "phase_reasons": tuple(str(v) for v in data.get("phase_reasons") or ()),
        "phase_history": tuple(
            dict(v) for v in data.get("phase_history") or () if isinstance(v, dict)
        ),
        "phase_coverage_score": _optional_float(data.get("phase_coverage_score")),
        "phase_conviction_score": _optional_float(data.get("phase_conviction_score")),
    }


# --- STRATEGY FIELDS ---

def _serialize_strategy_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "strategy_name": fp.strategy_name,
        "strategy_rule_name": fp.strategy_rule_name,
        "strategy_rule_outcome": fp.strategy_rule_outcome,
        "strategy_evidence_route": fp.strategy_evidence_route,
        "strategy_evidence_outcome": fp.strategy_evidence_outcome,
        "strategy_coverage_score": fp.strategy_coverage_score,
        "strategy_conviction_score": fp.strategy_conviction_score,
        "strategy_freshness_score": fp.strategy_freshness_score,
        "strategy_rationale": list(fp.strategy_rationale),
    }


def _parse_strategy_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": data.get("strategy_name"),
        "strategy_rule_name": data.get("strategy_rule_name"),
        "strategy_rule_outcome": data.get("strategy_rule_outcome"),
        "strategy_evidence_route": data.get("strategy_evidence_route"),
        "strategy_evidence_outcome": data.get("strategy_evidence_outcome"),
        "strategy_coverage_score": _optional_float(data.get("strategy_coverage_score")),
        "strategy_conviction_score": _optional_float(data.get("strategy_conviction_score")),
        "strategy_freshness_score": _optional_float(data.get("strategy_freshness_score")),
        "strategy_rationale": tuple(
            str(v) for v in data.get("strategy_rationale") or ()
        ),
    }


# --- FLOW FIELDS ---

def _serialize_flow_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "rsi": fp.rsi,
        "bb_width_pctile": fp.bb_width_pctile,
        "vwap_position": fp.vwap_position,
        "rs_vs_ihsg": fp.rs_vs_ihsg,
        "volume_ratio": fp.volume_ratio,
        "volume_dry_up_ratio": fp.volume_dry_up_ratio,
        "volume_expansion_ratio": fp.volume_expansion_ratio,
        "volume_dry_up_confirmed": fp.volume_dry_up_confirmed,
        "volume_expansion_confirmed": fp.volume_expansion_confirmed,
        "volume_trigger_confirmed": fp.volume_trigger_confirmed,
        "cnfb": fp.cnfb,
        "foreign_participation": fp.foreign_participation,
        "foreign_concentration": fp.foreign_concentration,
        "domestic_broker_accumulation": fp.domestic_broker_accumulation,
    }


def _parse_flow_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "rsi": _optional_float(data.get("rsi", data.get("rsi_at_signal"))),
        "bb_width_pctile": _optional_float(
            data.get("bb_width_pctile", data.get("bb_width_pctile_at_signal"))
        ),
        "vwap_position": _optional_float(
            data.get("vwap_position", data.get("vwap_position_at_signal"))
        ),
        "rs_vs_ihsg": _optional_float(
            data.get("rs_vs_ihsg", data.get("rs_vs_ihsg_20d_at_signal"))
        ),
        "volume_ratio": _optional_float(
            data.get("volume_ratio", data.get("volume_ratio_at_signal"))
        ),
        "volume_dry_up_ratio": _optional_float(
            data.get("volume_dry_up_ratio", data.get("volume_dry_up_ratio_at_signal"))
        ),
        "volume_expansion_ratio": _optional_float(
            data.get("volume_expansion_ratio", data.get("volume_expansion_ratio_at_signal"))
        ),
        "volume_dry_up_confirmed": _optional_bool(data.get("volume_dry_up_confirmed")),
        "volume_expansion_confirmed": _optional_bool(data.get("volume_expansion_confirmed")),
        "volume_trigger_confirmed": _optional_bool(data.get("volume_trigger_confirmed")),
        "cnfb": _optional_float(data.get("cnfb", data.get("cnfb_20d_at_signal"))),
        "foreign_participation": _optional_float(
            data.get(
                "foreign_participation",
                data.get("foreign_participation_at_signal"),
            )
        ),
        "foreign_concentration": _optional_float(
            data.get(
                "foreign_concentration",
                data.get("foreign_concentration_at_signal"),
            )
        ),
        "domestic_broker_accumulation": _optional_float(
            data.get(
                "domestic_broker_accumulation",
                data.get("domestic_broker_accumulation_at_signal"),
            )
        ),
    }


# --- REGIME FIELDS ---

def _serialize_regime_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "market_regime": dict(fp.market_regime),
        "market_regime_at_signal": fp.market_regime_at_signal,
        "regime_confidence_at_signal": fp.regime_confidence_at_signal,
        "regime_stability_at_signal": fp.regime_stability_at_signal,
        "days_in_regime_at_signal": fp.days_in_regime_at_signal,
        "regime_transition_warning_at_signal": fp.regime_transition_warning_at_signal,
        "regime_detection_method_at_signal": fp.regime_detection_method_at_signal,
        "coverage": fp.coverage,
        "conviction": fp.conviction,
    }


def _parse_regime_fields(data: dict[str, Any]) -> dict[str, Any]:
    regime = data.get("market_regime")
    if regime is None and data.get("market_regime_at_signal") is not None:
        regime = {
            "regime": data.get("market_regime_at_signal"),
            "regime_confidence": data.get("regime_confidence_at_signal"),
            "regime_stability": data.get("regime_stability_at_signal"),
        }
        if data.get("decision_constraints") is not None:
            regime["decision_constraints"] = data.get("decision_constraints")

    return {
        "market_regime": dict(regime or {}),
        "market_regime_at_signal": (
            data.get("market_regime_at_signal")
            or (regime.get("regime") if regime else None)
        ),
        "regime_confidence_at_signal": _optional_float(
            data.get("regime_confidence_at_signal")
            if data.get("regime_confidence_at_signal") is not None
            else (regime.get("regime_confidence") if regime else None)
        ),
        "regime_stability_at_signal": (
            data.get("regime_stability_at_signal")
            or (regime.get("regime_stability") if regime else None)
        ),
        "days_in_regime_at_signal": _optional_int(
            data.get("days_in_regime_at_signal")
            if data.get("days_in_regime_at_signal") is not None
            else (regime.get("days_in_regime") if regime else None)
        ),
        "regime_transition_warning_at_signal": (
            data.get("regime_transition_warning_at_signal")
            or (regime.get("transition_warning") if regime else None)
        ),
        "regime_detection_method_at_signal": data.get("regime_detection_method_at_signal"),
        "coverage": _optional_float(data.get("coverage", data.get("coverage_score"))),
        "conviction": _optional_float(data.get("conviction", data.get("conviction_score"))),
    }


# --- INSTITUTIONAL ACCUMULATION FIELDS ---


def _serialize_institutional_accumulation_fields(
    fp: "SignalObservationFingerprint",
) -> dict[str, Any]:
    return {
        "institutional_accumulation_status": fp.institutional_accumulation_status,
        "ia_foreign_participation": fp.ia_foreign_participation,
        "ia_foreign_cr4": fp.ia_foreign_cr4,
        "ia_foreign_cr8": fp.ia_foreign_cr8,
        "ia_cnfb_divergence_20d": fp.ia_cnfb_divergence_20d,
        "ia_cnfb_divergence_30d": fp.ia_cnfb_divergence_30d,
        "ia_cnfb_distribution_3d": fp.ia_cnfb_distribution_3d,
        "ia_foreign_vwap_distance": fp.ia_foreign_vwap_distance,
        "ia_foreign_track_coverage": fp.ia_foreign_track_coverage,
        "ia_foreign_track_conviction": fp.ia_foreign_track_conviction,
        "ia_domestic_broker_consistency": fp.ia_domestic_broker_consistency,
        "ia_domestic_broker_reversal": fp.ia_domestic_broker_reversal,
        "ia_domestic_accumulation_session_ratio": fp.ia_domestic_accumulation_session_ratio,
        "ia_domestic_buy_vwap_distance": fp.ia_domestic_buy_vwap_distance,
        "ia_domestic_broker_hhi_divergence": fp.ia_domestic_broker_hhi_divergence,
        "ia_bandar_broad_score_normalized": fp.ia_bandar_broad_score_normalized,
        "ia_domestic_track_coverage": fp.ia_domestic_track_coverage,
        "ia_domestic_track_conviction": fp.ia_domestic_track_conviction,
        "ia_counterparty_transfer_asymmetry": fp.ia_counterparty_transfer_asymmetry,
        "ia_counterparty_buy_hhi": fp.ia_counterparty_buy_hhi,
        "ia_counterparty_sell_hhi": fp.ia_counterparty_sell_hhi,
        "ia_coverage_score": fp.ia_coverage_score,
        "ia_conviction_score": fp.ia_conviction_score,
    }


def _parse_institutional_accumulation_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "institutional_accumulation_status": data.get("institutional_accumulation_status"),
        "ia_foreign_participation": _optional_float(data.get("ia_foreign_participation")),
        "ia_foreign_cr4": _optional_float(data.get("ia_foreign_cr4")),
        "ia_foreign_cr8": _optional_float(data.get("ia_foreign_cr8")),
        "ia_cnfb_divergence_20d": _optional_float(data.get("ia_cnfb_divergence_20d")),
        "ia_cnfb_divergence_30d": _optional_float(data.get("ia_cnfb_divergence_30d")),
        "ia_cnfb_distribution_3d": _optional_float(data.get("ia_cnfb_distribution_3d")),
        "ia_foreign_vwap_distance": _optional_float(data.get("ia_foreign_vwap_distance")),
        "ia_foreign_track_coverage": _optional_float(data.get("ia_foreign_track_coverage")),
        "ia_foreign_track_conviction": _optional_float(
            data.get("ia_foreign_track_conviction")
        ),
        "ia_domestic_broker_consistency": _optional_float(
            data.get("ia_domestic_broker_consistency")
        ),
        "ia_domestic_broker_reversal": _optional_float(data.get("ia_domestic_broker_reversal")),
        "ia_domestic_accumulation_session_ratio": _optional_float(
            data.get("ia_domestic_accumulation_session_ratio")
        ),
        "ia_domestic_buy_vwap_distance": _optional_float(
            data.get("ia_domestic_buy_vwap_distance")
        ),
        "ia_domestic_broker_hhi_divergence": _optional_float(
            data.get("ia_domestic_broker_hhi_divergence")
        ),
        "ia_bandar_broad_score_normalized": _optional_float(
            data.get("ia_bandar_broad_score_normalized")
        ),
        "ia_domestic_track_coverage": _optional_float(data.get("ia_domestic_track_coverage")),
        "ia_domestic_track_conviction": _optional_float(data.get("ia_domestic_track_conviction")),
        "ia_counterparty_transfer_asymmetry": _optional_float(
            data.get("ia_counterparty_transfer_asymmetry")
        ),
        "ia_counterparty_buy_hhi": _optional_float(data.get("ia_counterparty_buy_hhi")),
        "ia_counterparty_sell_hhi": _optional_float(data.get("ia_counterparty_sell_hhi")),
        "ia_coverage_score": _optional_float(data.get("ia_coverage_score")),
        "ia_conviction_score": _optional_float(data.get("ia_conviction_score")),
    }


# --- TICKER PROFILE FIELDS ---

def _serialize_ticker_profile_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "ticker_profile_label": fp.ticker_profile_label,
        "ticker_profile_confidence": fp.ticker_profile_confidence,
        "tp_market_tier": fp.tp_market_tier,
        "tp_foreign_institutional_exposure": fp.tp_foreign_institutional_exposure,
        "tp_domestic_bandar_exposure": fp.tp_domestic_bandar_exposure,
        "tp_retail_speculative_exposure": fp.tp_retail_speculative_exposure,
        "tp_liquidity_score": fp.tp_liquidity_score,
        "tp_broker_concentration_score": fp.tp_broker_concentration_score,
        "tp_foreign_flow_score": fp.tp_foreign_flow_score,
        "tp_volatility_score": fp.tp_volatility_score,
        "tp_index_membership_score": fp.tp_index_membership_score,
        "tp_market_cap_bucket": fp.tp_market_cap_bucket,
        "tp_sector": fp.tp_sector,
        "tp_index_memberships": fp.tp_index_memberships,
        "tp_coverage_score": fp.tp_coverage_score,
        "tp_epoch": fp.tp_epoch,
    }


def _parse_ticker_profile_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker_profile_label": data.get("ticker_profile_label"),
        "ticker_profile_confidence": _optional_float(data.get("ticker_profile_confidence")),
        "tp_market_tier": data.get("tp_market_tier"),
        "tp_foreign_institutional_exposure": _optional_float(
            data.get("tp_foreign_institutional_exposure")
        ),
        "tp_domestic_bandar_exposure": _optional_float(
            data.get("tp_domestic_bandar_exposure")
        ),
        "tp_retail_speculative_exposure": _optional_float(
            data.get("tp_retail_speculative_exposure")
        ),
        "tp_liquidity_score": _optional_float(data.get("tp_liquidity_score")),
        "tp_broker_concentration_score": _optional_float(
            data.get("tp_broker_concentration_score")
        ),
        "tp_foreign_flow_score": _optional_float(data.get("tp_foreign_flow_score")),
        "tp_volatility_score": _optional_float(data.get("tp_volatility_score")),
        "tp_index_membership_score": _optional_float(
            data.get("tp_index_membership_score")
        ),
        "tp_market_cap_bucket": data.get("tp_market_cap_bucket"),
        "tp_sector": data.get("tp_sector"),
        "tp_index_memberships": data.get("tp_index_memberships"),
        "tp_coverage_score": _optional_float(data.get("tp_coverage_score")),
        "tp_epoch": data.get("tp_epoch"),
    }


# --- SECTOR CONTEXT FIELDS ---

def _serialize_sector_context_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "sc_sector": fp.sc_sector,
        "sc_peer_count": fp.sc_peer_count,
        "sc_sector_20d_return": fp.sc_sector_20d_return,
        "sc_sector_vs_ihsg_20d": fp.sc_sector_vs_ihsg_20d,
        "sc_sector_breadth": fp.sc_sector_breadth,
        "sc_ticker_vs_sector_rs": fp.sc_ticker_vs_sector_rs,
        "sc_sector_regime": fp.sc_sector_regime,
        "sc_coverage_score": fp.sc_coverage_score,
    }


def _parse_sector_context_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "sc_sector": data.get("sc_sector"),
        "sc_peer_count": _optional_int(data.get("sc_peer_count")),
        "sc_sector_20d_return": _optional_float(data.get("sc_sector_20d_return")),
        "sc_sector_vs_ihsg_20d": _optional_float(data.get("sc_sector_vs_ihsg_20d")),
        "sc_sector_breadth": _optional_float(data.get("sc_sector_breadth")),
        "sc_ticker_vs_sector_rs": _optional_float(data.get("sc_ticker_vs_sector_rs")),
        "sc_sector_regime": data.get("sc_sector_regime"),
        "sc_coverage_score": _optional_float(data.get("sc_coverage_score")),
    }


# --- COMPANY QUALITY FIELDS ---

def _serialize_company_quality_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "cq_valuation_score": fp.cq_valuation_score,
        "cq_earnings_trend_score": fp.cq_earnings_trend_score,
        "cq_analyst_score": fp.cq_analyst_score,
        "cq_insider_score": fp.cq_insider_score,
        "cq_seasonality_score": fp.cq_seasonality_score,
        "cq_aggregate_score": fp.cq_aggregate_score,
        "cq_coverage_score": fp.cq_coverage_score,
        "cq_present_axis_count": fp.cq_present_axis_count,
    }


def _parse_company_quality_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "cq_valuation_score": _optional_float(data.get("cq_valuation_score")),
        "cq_earnings_trend_score": _optional_float(data.get("cq_earnings_trend_score")),
        "cq_analyst_score": _optional_float(data.get("cq_analyst_score")),
        "cq_insider_score": _optional_float(data.get("cq_insider_score")),
        "cq_seasonality_score": _optional_float(data.get("cq_seasonality_score")),
        "cq_aggregate_score": _optional_float(data.get("cq_aggregate_score")),
        "cq_coverage_score": _optional_float(data.get("cq_coverage_score")),
        "cq_present_axis_count": _optional_int(data.get("cq_present_axis_count")),
    }


# --- ALPHA/TRIGGER FIELDS ---

def _serialize_alpha_trigger_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "alpha_score": fp.alpha_score,
        "trigger_score": fp.trigger_score,
        "alpha_trigger_final_exact_score": fp.alpha_trigger_final_exact_score,
        "alpha_trigger_horizon": fp.alpha_trigger_horizon,
        "alpha_trigger_alpha_weight": fp.alpha_trigger_alpha_weight,
        "flow_trigger_allowed": fp.flow_trigger_allowed,
        "alpha_trigger_route_metadata": [
            dict(v) for v in fp.alpha_trigger_route_metadata
        ],
        "alpha_trigger_unavailable_reasons": list(
            fp.alpha_trigger_unavailable_reasons
        ),
    }


def _parse_alpha_trigger_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "alpha_score": _optional_float(data.get("alpha_score")),
        "trigger_score": _optional_float(data.get("trigger_score")),
        "alpha_trigger_final_exact_score": _optional_float(
            data.get("alpha_trigger_final_exact_score")
        ),
        "alpha_trigger_horizon": data.get("alpha_trigger_horizon"),
        "alpha_trigger_alpha_weight": _optional_float(
            data.get("alpha_trigger_alpha_weight")
        ),
        "flow_trigger_allowed": _optional_bool(data.get("flow_trigger_allowed")),
        "alpha_trigger_route_metadata": tuple(
            dict(v)
            for v in data.get("alpha_trigger_route_metadata") or ()
            if isinstance(v, dict)
        ),
        "alpha_trigger_unavailable_reasons": tuple(
            str(v) for v in data.get("alpha_trigger_unavailable_reasons") or ()
        ),
    }


# --- VOLATILITY FIELDS ---

def _serialize_volatility_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "atr_at_signal": fp.atr_at_signal,
        "atr_pct_at_signal": fp.atr_pct_at_signal,
        "volatility_bucket_at_signal": fp.volatility_bucket_at_signal,
        "volatility_size_multiplier_at_signal": fp.volatility_size_multiplier_at_signal,
    }


def _parse_volatility_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "atr_at_signal": _optional_float(
            data.get("atr_at_signal", data.get("atr_20"))
        ),
        "atr_pct_at_signal": _optional_float(
            data.get("atr_pct_at_signal", data.get("atr_pct"))
        ),
        "volatility_bucket_at_signal": (
            data.get("volatility_bucket_at_signal", data.get("volatility_bucket"))
        ),
        "volatility_size_multiplier_at_signal": _optional_float(
            data.get(
                "volatility_size_multiplier_at_signal",
                data.get("volatility_size_multiplier"),
            )
        ),
    }
