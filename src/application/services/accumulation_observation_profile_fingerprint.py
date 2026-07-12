"""Ticker profile, sector context, and company quality fingerprint serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


def _tp_fingerprint(
    tp: "TickerProfileSnapshot | None",
) -> dict:
    _none: dict = {
        "ticker_profile_label": None,
        "ticker_profile_confidence": None,
        "tp_market_tier": None,
        "tp_foreign_institutional_exposure": None,
        "tp_domestic_bandar_exposure": None,
        "tp_retail_speculative_exposure": None,
        "tp_liquidity_score": None,
        "tp_broker_concentration_score": None,
        "tp_foreign_flow_score": None,
        "tp_volatility_score": None,
        "tp_index_membership_score": None,
        "tp_market_cap_bucket": None,
        "tp_sector": None,
        "tp_index_memberships": None,
        "tp_coverage_score": None,
        "tp_epoch": None,
    }
    if tp is None:
        return _none
    return {
        "ticker_profile_label": tp.primary_profile,
        "ticker_profile_confidence": tp.profile_confidence,
        "tp_market_tier": tp.market_tier,
        "tp_foreign_institutional_exposure": tp.foreign_institutional_exposure,
        "tp_domestic_bandar_exposure": tp.domestic_bandar_exposure,
        "tp_retail_speculative_exposure": tp.retail_speculative_exposure,
        "tp_liquidity_score": tp.liquidity_score,
        "tp_broker_concentration_score": tp.broker_concentration_score,
        "tp_foreign_flow_score": tp.foreign_flow_score,
        "tp_volatility_score": tp.volatility_score,
        "tp_index_membership_score": tp.index_membership_score,
        "tp_market_cap_bucket": tp.market_cap_bucket or "UNKNOWN",
        "tp_sector": tp.sector,
        "tp_index_memberships": ",".join(tp.index_memberships) if tp.index_memberships else None,
        "tp_coverage_score": tp.coverage_score,
        "tp_epoch": tp.epoch,
    }


def _sc_fingerprint(
    sc: "SectorContextEvidence | None",
) -> dict:
    _none: dict = {
        "sc_sector": None,
        "sc_peer_count": None,
        "sc_sector_20d_return": None,
        "sc_sector_vs_ihsg_20d": None,
        "sc_sector_breadth": None,
        "sc_ticker_vs_sector_rs": None,
        "sc_sector_regime": None,
        "sc_coverage_score": None,
    }
    if sc is None:
        return _none
    return {
        "sc_sector": sc.sector,
        "sc_peer_count": sc.peer_count,
        "sc_sector_20d_return": sc.sector_20d_return,
        "sc_sector_vs_ihsg_20d": sc.sector_vs_ihsg_20d,
        "sc_sector_breadth": sc.sector_breadth,
        "sc_ticker_vs_sector_rs": sc.ticker_vs_sector_rs,
        "sc_sector_regime": sc.sector_regime,
        "sc_coverage_score": sc.coverage_score,
    }


def _cq_fingerprint(
    cq: "CompanyQualityContextEvidence | None",
) -> dict:
    _none: dict = {
        "cq_valuation_score": None,
        "cq_earnings_trend_score": None,
        "cq_analyst_score": None,
        "cq_insider_score": None,
        "cq_seasonality_score": None,
        "cq_aggregate_score": None,
        "cq_coverage_score": None,
        "cq_present_axis_count": None,
    }
    if cq is None:
        return _none
    return {
        "cq_valuation_score": cq.valuation_score,
        "cq_earnings_trend_score": cq.earnings_trend_score,
        "cq_analyst_score": cq.analyst_score,
        "cq_insider_score": cq.insider_score,
        "cq_seasonality_score": cq.seasonality_score,
        "cq_aggregate_score": cq.aggregate_score,
        "cq_coverage_score": cq.coverage_score,
        "cq_present_axis_count": len(cq.present_axes),
    }
