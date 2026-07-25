"""
Pre-open signal evidence groups (ADR-048).

Contract: ``pre_open_signal_evidence.v1``

- ``AuctionNcpEvidence`` — NCP-locked auction quality (required for production).
- ``OpenViabilityEvidence`` — 30m trap / friction flags (veto-only in v1 cascade).

Not multi-day flow authority. Pure domain VOs; no I/O.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT = "pre_open_signal_evidence.v1"
PRE_OPEN_HORIZON = "open_30m"
PRE_OPEN_SETUP_FAMILY = "open_call_participation"


@dataclass(frozen=True)
class AuctionNcpProvenance:
    """Provenance for one auction_ncp evidence binding."""

    ticker: str
    decision_at: datetime | None
    capture_phase: str  # e.g. NCP_LOCKED, PRE_NCP, UNKNOWN
    snapshot_ref: str | None = None
    trade_date: date | None = None


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
