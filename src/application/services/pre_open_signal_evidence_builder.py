"""Build pre-open signal evidence groups from a ScreenerCandidate.

Maps already-computed plan/microstructure fields into ADR-048 evidence VOs.
Does not call engines or fabricate NCP rows.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.domain.value_objects.pre_open_signal_evidence import (
    AuctionNcpEvidence,
    AuctionNcpProvenance,
    OpenViabilityEvidence,
    PreOpenSignalEvidenceBundle,
)


def build_pre_open_signal_evidence(
    candidate: Any,
    *,
    trade_date: date,
    decision_at: datetime | None = None,
    capture_phase: str = "UNKNOWN",
    snapshot_ref: str | None = None,
    config: PreOpenSignalConfig | None = None,
) -> PreOpenSignalEvidenceBundle:
    """Build evidence bundle from a duck-typed pre-open candidate."""
    cfg = config or PreOpenSignalConfig()
    ticker = str(getattr(candidate, "ticker", "") or "")
    iev = int(getattr(candidate, "iev", 0) or 0)
    prev_close = getattr(candidate, "prev_close", None)
    gap_pct = getattr(candidate, "gap_pct", None)

    auction: AuctionNcpEvidence | None = None
    # Minimal auction presence: positive IEV + prior close (auction map anchor).
    if ticker and iev > 0 and prev_close is not None and prev_close > 0:
        auction = AuctionNcpEvidence(
            ticker=ticker,
            iev=iev,
            gap_pct=gap_pct if isinstance(gap_pct, Decimal) else (
                Decimal(str(gap_pct)) if gap_pct is not None else None
            ),
            bid_pressure=getattr(candidate, "bid_offer_imbalance", None),
            spread_pct=getattr(candidate, "spread_pct", None),
            prev_close=prev_close if isinstance(prev_close, Decimal) else Decimal(
                str(prev_close)
            ),
            provenance=AuctionNcpProvenance(
                ticker=ticker,
                decision_at=decision_at,
                capture_phase=capture_phase,
                snapshot_ref=snapshot_ref,
                trade_date=trade_date,
            ),
        )

    viability: OpenViabilityEvidence | None = None
    if ticker:
        gap_for_veto = gap_pct
        if gap_for_veto is not None and not isinstance(gap_for_veto, Decimal):
            gap_for_veto = Decimal(str(gap_for_veto))
        gap_out = bool(
            gap_for_veto is not None and abs(gap_for_veto) > cfg.gap_out_abs_pct
        )
        trend = getattr(candidate, "trend_signal", None)
        if trend == "GAP_OUT":
            gap_out = True

        spread = getattr(candidate, "spread_pct", None)
        friction_fail = False
        if spread is not None:
            sp = spread if isinstance(spread, Decimal) else Decimal(str(spread))
            friction_fail = sp > cfg.max_spread_pct

        rsi = getattr(candidate, "rsi", None)
        rsi_extension = bool(
            rsi is not None and rsi > cfg.rsi_extension_threshold
        )

        viability = OpenViabilityEvidence(
            ticker=ticker,
            gap_out=gap_out,
            friction_fail=friction_fail,
            unusual_volume=bool(getattr(candidate, "unusual_volume", False)),
            rsi_extension=rsi_extension,
            trend_signal=trend,
            iev_intensity=getattr(candidate, "iev_intensity", None),
            atr=getattr(candidate, "atr", None),
            gap_pct=gap_for_veto,
        )

    return PreOpenSignalEvidenceBundle(
        auction_ncp=auction,
        open_viability=viability,
    )
