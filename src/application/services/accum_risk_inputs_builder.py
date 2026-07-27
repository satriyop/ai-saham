"""Accum RiskInputsBuilder — GateContext from pre-loaded candidate enrichment.

Layer: Application
"""

from __future__ import annotations

from datetime import date

from src.domain.rules.risk_gate import GateContext


class AccumRiskInputsBuilder:
    """Pre-built GateContext from accumulation candidate fields (no N+1)."""

    def build(
        self,
        candidate: object,
        *,
        as_of_date: date,
    ) -> GateContext | None:
        ticker = getattr(candidate, "ticker", None)
        if not isinstance(ticker, str) or not ticker:
            raise TypeError("candidate must expose a string ticker")

        fundamentals = getattr(candidate, "fundamentals", None)
        shareholding = getattr(candidate, "shareholding", None)
        bandar = getattr(candidate, "bandar_detector", None)

        return GateContext(
            ticker=ticker,
            snapshot_date=as_of_date,
            piotroski_f_score=(
                fundamentals.piotroski_f_score if fundamentals is not None else None
            ),
            market_cap_idr=(fundamentals.market_cap_idr if fundamentals is not None else None),
            free_float_pct=(shareholding.free_float_pct if shareholding is not None else None),
            five_day_accdist=(bandar.five_day_accdist if bandar is not None else None),
        )
