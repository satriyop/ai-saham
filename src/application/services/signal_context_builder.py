"""
SignalContext builder helpers.

Layer: Application

Builds the non-authoritative SignalContext enrichment bundle from a
duck-typed candidate (any object exposing the optional enrichment fields).
Does not supply canonical setup/flow evidence — that remains scenario-owned
(ADR-041 / ADR-047).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.domain.value_objects.signal_assessment import SignalContext


def build_signal_context_from_candidate(
    *,
    ticker: str,
    snapshot_date: date,
    candidate: Any,
    signal_engine: Any,
) -> SignalContext:
    """Build SignalContext from a candidate's optional enrichment fields.

    Scenario-agnostic: every field is read via getattr / optional nested
    objects. Absent ``accum_score`` yields ``foreign_flow_quality=None``
    (no fabrication). Authority for the weighted Setup/Flow score remains
    ``canonical_evidence``, not this bundle.
    """
    bd = getattr(candidate, "bandar_detector", None)
    se = getattr(candidate, "seasonal_edge", None)
    ac = getattr(candidate, "analyst_consensus", None)
    fe = getattr(candidate, "forward_estimates", None)

    num_optional = (
        sum(
            1
            for x in [bd.top3_accdist, bd.top5_accdist, bd.top10_accdist]
            if x is not None
        )
        if bd is not None
        else 0
    )

    forward_pe = fe.forward_pe if fe else None
    current_price = getattr(candidate, "current_price", None)
    if forward_pe is None and fe is not None and current_price is not None and current_price > 0:
        forward_pe = fe.with_current_price(float(current_price)).forward_pe

    accum_score = getattr(candidate, "accum_score", None)
    foreign_flow_quality = (
        signal_engine.foreign_flow_quality_from_accum_score(accum_score)
        if accum_score is not None
        else None
    )

    return SignalContext(
        ticker=ticker,
        snapshot_date=snapshot_date,
        foreign_flow_quality=foreign_flow_quality,
        bandar_broad_score=bd.broad_score if bd else None,
        bandar_max_range=signal_engine.bandar_max_range(num_optional)
        if bd
        else signal_engine.bandar_max_range(0),
        insider_net_buy_ratio=getattr(candidate, "insider_net_buy_ratio", None),
        seasonality_win_rate=se.win_rate_pct if se else None,
        seasonality_avg_return_pct=se.avg_monthly_return_pct if se else None,
        seasonality_total_years=se.total_years if se else None,
        seasonality_back_years=se.back_years if se else None,
        analyst_buy_pct=ac.buy_ratio if ac else None,
        analyst_upside_pct=ac.upside_pct if ac else None,
        forward_pe=forward_pe,
    )
