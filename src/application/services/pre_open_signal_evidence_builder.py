"""Build pre-open signal evidence groups from a ScreenerCandidate.

Maps already-computed plan/microstructure fields into ADR-048 evidence VOs.
Does not call engines or fabricate NCP rows.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)
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
    collection_started_at: datetime | None = None,
    decision_at: datetime | None = None,
    capture_phase: str = "UNKNOWN",
    source_is_live: bool = False,
    snapshot_ref: str | None = None,
    config: PreOpenDirectionalBaselineConfig | None = None,
    delta_iev: int | None = None,
) -> PreOpenSignalEvidenceBundle:
    """Build evidence bundle from a duck-typed pre-open candidate.

    ``delta_iev`` may be passed explicitly (from locked-input history) or read from
    ``candidate.delta_iev`` when present. None = MISSING (do not fabricate).
    """
    cfg = config or PreOpenDirectionalBaselineConfig()
    ticker = str(getattr(candidate, "ticker", "") or "")
    iev = int(getattr(candidate, "iev", 0) or 0)
    prev_close = getattr(candidate, "prev_close", None)
    gap_pct = getattr(candidate, "gap_pct", None)
    resolved_delta: int | None = delta_iev
    if resolved_delta is None and hasattr(candidate, "delta_iev"):
        raw = getattr(candidate, "delta_iev", None)
        if raw is not None:
            try:
                resolved_delta = int(raw)
            except (TypeError, ValueError):
                resolved_delta = None

    auction: AuctionNcpEvidence | None = None
    provenance = AuctionNcpProvenance(
        ticker=ticker,
        collection_started_at=collection_started_at,
        decision_at=decision_at,
        capture_phase=capture_phase,
        source_is_live=source_is_live,
        snapshot_ref=snapshot_ref,
        trade_date=trade_date,
    )
    # Production auction evidence requires positive auction data plus proven,
    # same-session NCP provenance. Pre-NCP/unknown snapshots remain discovery-only.
    if (
        ticker
        and iev > 0
        and prev_close is not None
        and prev_close > 0
        and provenance.is_production_ncp
    ):
        auction = AuctionNcpEvidence(
            ticker=ticker,
            iev=iev,
            gap_pct=(
                gap_pct
                if isinstance(gap_pct, Decimal)
                else (Decimal(str(gap_pct)) if gap_pct is not None else None)
            ),
            bid_pressure=getattr(candidate, "bid_offer_imbalance", None),
            spread_pct=getattr(candidate, "spread_pct", None),
            prev_close=prev_close if isinstance(prev_close, Decimal) else Decimal(str(prev_close)),
            provenance=provenance,
            iep=getattr(candidate, "iep", None),
            iep_gap_pct=getattr(candidate, "iep_gap_pct", None),
            bid_gap_pct=getattr(candidate, "bid_gap_pct", None),
            gap_price_source=getattr(candidate, "gap_price_source", None),
            delta_iev=resolved_delta,
        )

    viability: OpenViabilityEvidence | None = None
    if ticker:
        gap_for_veto = gap_pct
        if gap_for_veto is not None and not isinstance(gap_for_veto, Decimal):
            gap_for_veto = Decimal(str(gap_for_veto))
        gap_out = bool(gap_for_veto is not None and abs(gap_for_veto) > cfg.large_gap_caution_pct)
        trend = getattr(candidate, "trend_signal", None)
        if trend == "GAP_OUT":
            gap_out = True

        spread = getattr(candidate, "spread_pct", None)
        friction_fail = False
        if spread is not None:
            sp = spread if isinstance(spread, Decimal) else Decimal(str(spread))
            friction_fail = sp > cfg.max_spread_pct

        rsi = getattr(candidate, "rsi", None)
        rsi_extension = bool(rsi is not None and rsi > cfg.rsi_extension_threshold)

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
