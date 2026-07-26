"""
Pre-open signal evidence groups (ADR-048).

Contract: ``pre_open_signal_evidence.v2``

- ``AuctionNcpEvidence`` — NCP-locked auction quality (required for production).
- ``OpenViabilityEvidence`` — 30m trap / friction flags (veto-only in v1 cascade).

Not multi-day flow authority. Pure domain VOs; no I/O.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    NCP_LOCK_TIME,
    REGULAR_OPEN,
)

PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT = "pre_open_signal_evidence.v2"
PRE_OPEN_HORIZON = "open_30m"
PRE_OPEN_SETUP_FAMILY = "open_call_participation"


@dataclass(frozen=True)
class AuctionNcpProvenance:
    """Provenance for one auction_ncp evidence binding."""

    ticker: str
    collection_started_at: datetime | None
    decision_at: datetime | None
    capture_phase: str  # e.g. NCP_LOCKED, PRE_NCP, UNKNOWN
    source_is_live: bool
    snapshot_ref: str | None = None
    trade_date: date | None = None

    @property
    def is_production_ncp(self) -> bool:
        """Whether this provenance proves a same-session NCP decision snapshot."""
        if self.capture_phase != "NCP_LOCKED":
            return False
        if not self.source_is_live:
            return False
        if (
            self.collection_started_at is None
            or self.collection_started_at.tzinfo is None
            or self.decision_at is None
            or self.decision_at.tzinfo is None
        ):
            return False
        if not self.snapshot_ref or not self.snapshot_ref.strip():
            return False

        local_collection_started_at = self.collection_started_at.astimezone(
            IDX_TIMEZONE
        )
        local_decision_at = self.decision_at.astimezone(IDX_TIMEZONE)
        if (
            self.trade_date is None
            or self.trade_date != local_collection_started_at.date()
            or self.trade_date != local_decision_at.date()
        ):
            return False
        return (
            NCP_LOCK_TIME <= local_collection_started_at.time()
            and local_collection_started_at <= local_decision_at
            and local_decision_at.time() < REGULAR_OPEN
        )


@dataclass(frozen=True)
class AuctionNcpEvidence:
    """NCP-locked auction group (production-required for pre-open signal)."""

    ticker: str
    iev: int
    gap_pct: Decimal | None
    bid_pressure: float | None  # bid_lots / (bid+offer); None if unknown
    spread_pct: Decimal | None
    prev_close: Decimal | None
    provenance: AuctionNcpProvenance
    # Build-into-lock appetite: last_iev − first_iev same day (multi-tick history).
    # None = MISSING (not enough ticks) — never fabricate; scorer must not fail closed.
    delta_iev: int | None = None

    def __post_init__(self) -> None:
        if self.iev < 0:
            raise ValueError(f"iev must be >= 0, got {self.iev}")
        if self.provenance.ticker != self.ticker:
            raise ValueError(
                "auction_ncp provenance ticker must match evidence ticker"
            )
        if not self.provenance.is_production_ncp:
            raise ValueError(
                "auction_ncp requires a verified live source and timezone-aware "
                "collection window wholly inside the same-session NCP_LOCKED "
                "phase with a snapshot_ref"
            )
        if self.bid_pressure is not None and not (0.0 <= self.bid_pressure <= 1.0):
            raise ValueError(
                f"bid_pressure must be 0.0–1.0, got {self.bid_pressure}"
            )


@dataclass(frozen=True)
class OpenViabilityEvidence:
    """Open-viability / trap group (veto-only in v1 cascade)."""

    ticker: str
    gap_out: bool
    friction_fail: bool
    unusual_volume: bool
    rsi_extension: bool
    trend_signal: str | None
    iev_intensity: float | None
    atr: Decimal | None
    gap_pct: Decimal | None


@dataclass(frozen=True)
class PreOpenSignalEvidenceBundle:
    """Scenario bundle: auction required for production; viability optional."""

    auction_ncp: AuctionNcpEvidence | None
    open_viability: OpenViabilityEvidence | None
    evidence_contract_version: str = PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT
    horizon: str = PRE_OPEN_HORIZON
