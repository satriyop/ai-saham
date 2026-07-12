"""Institutional accumulation evidence fingerprint serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )


def _ia_evidence_fingerprint(
    ia_evidence: "InstitutionalAccumulationEvidence | None",
) -> dict:
    _none: dict = {
        "institutional_accumulation_status": None,
        "ia_foreign_participation": None,
        "ia_foreign_cr4": None,
        "ia_foreign_cr8": None,
        "ia_cnfb_divergence_20d": None,
        "ia_cnfb_divergence_30d": None,
        "ia_cnfb_distribution_3d": None,
        "ia_foreign_vwap_distance": None,
        "ia_foreign_track_coverage": None,
        "ia_foreign_track_conviction": None,
        "ia_domestic_broker_consistency": None,
        "ia_domestic_broker_reversal": None,
        "ia_domestic_accumulation_session_ratio": None,
        "ia_domestic_buy_vwap_distance": None,
        "ia_domestic_broker_hhi_divergence": None,
        "ia_bandar_broad_score_normalized": None,
        "ia_domestic_track_coverage": None,
        "ia_domestic_track_conviction": None,
        "ia_counterparty_transfer_asymmetry": None,
        "ia_counterparty_buy_hhi": None,
        "ia_counterparty_sell_hhi": None,
        "ia_coverage_score": None,
        "ia_conviction_score": None,
    }
    if ia_evidence is None:
        return _none
    ft = ia_evidence.foreign_institutional_track
    dt = ia_evidence.domestic_bandar_track
    ct = ia_evidence.counterparty_transfer
    meta = ia_evidence.metadata or {}
    bullish = meta.get("cnfb_bullish_scores") or {}
    bearish = meta.get("cnfb_bearish_scores") or {}
    return {
        "institutional_accumulation_status": ia_evidence.evidence_status.value,
        "ia_foreign_participation": ft.foreign_participation_score,
        "ia_foreign_cr4": ft.foreign_cr4_score,
        "ia_foreign_cr8": ft.foreign_cr8_score,
        "ia_cnfb_divergence_20d": bullish.get("cnfb_20d"),
        "ia_cnfb_divergence_30d": bullish.get("cnfb_30d"),
        "ia_cnfb_distribution_3d": bearish.get("cnfb_3d"),
        "ia_foreign_vwap_distance": ft.foreign_vwap_distance_score,
        "ia_foreign_track_coverage": ft.coverage_score,
        "ia_foreign_track_conviction": ft.conviction_score,
        "ia_domestic_broker_consistency": dt.broker_consistency_score,
        "ia_domestic_broker_reversal": dt.broker_reversal_score,
        "ia_domestic_accumulation_session_ratio": dt.accumulation_session_ratio,
        "ia_domestic_buy_vwap_distance": dt.domestic_buy_vwap_distance_score,
        "ia_domestic_broker_hhi_divergence": dt.broker_hhi_divergence_score,
        "ia_bandar_broad_score_normalized": dt.bandar_broad_score_normalized,
        "ia_domestic_track_coverage": dt.coverage_score,
        "ia_domestic_track_conviction": dt.conviction_score,
        "ia_counterparty_transfer_asymmetry": ct.transfer_asymmetry_score if ct else None,
        "ia_counterparty_buy_hhi": ct.buy_side_hhi if ct else None,
        "ia_counterparty_sell_hhi": ct.sell_side_hhi if ct else None,
        "ia_coverage_score": ia_evidence.coverage_score,
        "ia_conviction_score": ia_evidence.conviction_score,
    }
