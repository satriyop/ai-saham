"""Context-section serialization for SignalObservationFingerprint.

Covers institutional accumulation, ticker profile, sector context, and
company quality fields.
"""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import _optional_float, _optional_int

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


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
        "ia_foreign_track_conviction": _optional_float(data.get("ia_foreign_track_conviction")),
        "ia_domestic_broker_consistency": _optional_float(
            data.get("ia_domestic_broker_consistency")
        ),
        "ia_domestic_broker_reversal": _optional_float(data.get("ia_domestic_broker_reversal")),
        "ia_domestic_accumulation_session_ratio": _optional_float(
            data.get("ia_domestic_accumulation_session_ratio")
        ),
        "ia_domestic_buy_vwap_distance": _optional_float(data.get("ia_domestic_buy_vwap_distance")),
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
        "tp_domestic_bandar_exposure": _optional_float(data.get("tp_domestic_bandar_exposure")),
        "tp_retail_speculative_exposure": _optional_float(
            data.get("tp_retail_speculative_exposure")
        ),
        "tp_liquidity_score": _optional_float(data.get("tp_liquidity_score")),
        "tp_broker_concentration_score": _optional_float(data.get("tp_broker_concentration_score")),
        "tp_foreign_flow_score": _optional_float(data.get("tp_foreign_flow_score")),
        "tp_volatility_score": _optional_float(data.get("tp_volatility_score")),
        "tp_index_membership_score": _optional_float(data.get("tp_index_membership_score")),
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
