"""Sector context evidence — local-universe sector diagnostics (Phase H).

DIAGNOSTIC-ONLY: persisted at observation time for replay and attribution.
May feed the Alpha/Trigger market_context slot as coverage/diagnostic evidence,
but DIAGNOSTIC authority prevents scoring impact. Never affects DecisionPolicy.

All sector metrics are computed from local candles of same-sector tickers
derived from universes.yaml sector groups. No external sector-index provider
is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


@dataclass(frozen=True)
class SectorContextEvidence:
    """
    Local-universe sector context evidence for a single ticker.

    Fields
    ------
    sector                 Sector label from ticker metadata (e.g. "Finance").
    peer_count             Number of same-sector peers whose candles were available.
    peer_tickers           Peer tickers used in computation (capped at builder max).
    sector_20d_return      Equal-weight average 20-session return across peers.
    sector_vs_ihsg_20d     sector_20d_return minus the IHSG 20-session return.
                           None when IHSG return is unavailable.
    sector_breadth         Fraction of peers with a positive 20-session return
                           (0.0–1.0). None when fewer than min_peer_count available.
    ticker_vs_sector_rs    Ticker 20-session return minus sector_20d_return.
                           None when either is unavailable.
    sector_regime          BULLISH | NEUTRAL | BEARISH | UNKNOWN.
    coverage_score         available_peers / max(min_peer_count, available_peers).
    evidence_status        Always DIAGNOSTIC in Phase H.
    reasons                Human-readable reason strings.
    unavailable_reasons    Why specific sub-metrics could not be computed.
    metadata               Optional raw sub-values for diagnostics.
    """

    sector: str | None
    peer_count: int
    peer_tickers: tuple[str, ...]
    sector_20d_return: float | None
    sector_vs_ihsg_20d: float | None
    sector_breadth: float | None
    ticker_vs_sector_rs: float | None
    sector_regime: str                  # BULLISH | NEUTRAL | BEARISH | UNKNOWN
    coverage_score: float               # [0, 1]
    evidence_status: EvidenceStatus     # always DIAGNOSTIC in Phase H
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.coverage_score <= 1.0):
            raise ValueError(
                f"coverage_score must be in [0,1], got {self.coverage_score}"
            )
        if self.sector_regime not in {"BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN"}:
            raise ValueError(f"invalid sector_regime: {self.sector_regime!r}")
        if self.sector_20d_return is not None and not (
            -1.0 <= self.sector_20d_return <= 5.0
        ):
            raise ValueError(
                f"sector_20d_return {self.sector_20d_return:.4f} outside plausible range"
            )
        if self.sector_breadth is not None and not (
            0.0 <= self.sector_breadth <= 1.0
        ):
            raise ValueError(
                f"sector_breadth must be in [0,1], got {self.sector_breadth}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "peer_count": self.peer_count,
            "peer_tickers": list(self.peer_tickers),
            "sector_20d_return": (
                round(self.sector_20d_return, 6)
                if self.sector_20d_return is not None else None
            ),
            "sector_vs_ihsg_20d": (
                round(self.sector_vs_ihsg_20d, 6)
                if self.sector_vs_ihsg_20d is not None else None
            ),
            "sector_breadth": (
                round(self.sector_breadth, 4)
                if self.sector_breadth is not None else None
            ),
            "ticker_vs_sector_rs": (
                round(self.ticker_vs_sector_rs, 6)
                if self.ticker_vs_sector_rs is not None else None
            ),
            "sector_regime": self.sector_regime,
            "coverage_score": round(self.coverage_score, 4),
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectorContextEvidence":
        return cls(
            sector=data.get("sector"),
            peer_count=data.get("peer_count", 0),
            peer_tickers=tuple(data.get("peer_tickers") or []),
            sector_20d_return=data.get("sector_20d_return"),
            sector_vs_ihsg_20d=data.get("sector_vs_ihsg_20d"),
            sector_breadth=data.get("sector_breadth"),
            ticker_vs_sector_rs=data.get("ticker_vs_sector_rs"),
            sector_regime=data.get("sector_regime", "UNKNOWN"),
            coverage_score=data.get("coverage_score", 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status", EvidenceStatus.DIAGNOSTIC.value)
            ),
            reasons=tuple(data.get("reasons") or []),
            unavailable_reasons=tuple(data.get("unavailable_reasons") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def unavailable(cls, *, reason: str) -> "SectorContextEvidence":
        return cls(
            sector=None,
            peer_count=0,
            peer_tickers=(),
            sector_20d_return=None,
            sector_vs_ihsg_20d=None,
            sector_breadth=None,
            ticker_vs_sector_rs=None,
            sector_regime="UNKNOWN",
            coverage_score=0.0,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(reason,),
        )
