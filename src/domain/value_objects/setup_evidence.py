"""
Setup evidence value object.

Diagnostic evidence contract for swing setup/timing structure. Introduced in
Phase 2 of the SignalEngine refactor. Captures the setup gate result and the
technical structure (trend, RSI, volatility compression, VWAP positioning)
alongside date-gated relative-strength and source-confidence-gated volume
sub-signals.

This object carries NO scoring or setup-policy logic — it is a descriptive
record produced by SetupEvidenceBuilder (application layer) from a
SetupEvaluation and an AccumulationCandidate that already exist. SignalEngine
does NOT consume this until Phase 4.

Layer: Domain
Depends on: stdlib only (dataclasses, datetime) + Freshness from factor_evidence
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.value_objects.factor_evidence import Freshness

_VALID_MATCH = {"MATCH", "PARTIAL", "NO_MATCH"}
_VALID_STRENGTH = {100.0, 60.0, 20.0}


@dataclass(frozen=True)
class SetupEvidence:
    """Immutable diagnostic record for a swing setup's structure."""

    ticker: str
    snapshot_date: date
    # Setup gate result (translated from SetupEvaluation)
    setup_name: str | None
    setup_match: str          # "MATCH" | "PARTIAL" | "NO_MATCH"
    match_strength: float     # MATCH→100.0, PARTIAL→60.0, NO_MATCH→20.0
    failed_gates: tuple[str, ...]
    # Technical structure (from AccumulationCandidate)
    trend: str | None         # "UP" | "DOWN" | "SIDE"
    rsi: float | None
    bb_width_pctile: float | None  # 0–1; lower = tighter volatility compression
    vwap_discount_pct: float | None
    vwap_pct: float | None
    # RS vs IHSG sub-signal (pre-computed by caller; date-gated at 2025-07-01)
    rs_vs_ihsg_5d: float | None  # None when date-gated or unavailable
    rs_freshness: Freshness
    # Volume trend sub-signal (source-confidence-gated; stockbit only)
    volume_trend_ratio: float | None  # 5d/20d volume ratio; None when source is not stockbit
    volume_freshness: Freshness
    candle_source: str | None    # "stockbit" | "yahoo" | "yahoo_inferred" | None

    def __post_init__(self) -> None:
        if self.match_strength not in _VALID_STRENGTH:
            raise ValueError(
                f"SetupEvidence match_strength must be one of {_VALID_STRENGTH}, "
                f"got {self.match_strength}"
            )
        if self.setup_match not in _VALID_MATCH:
            raise ValueError(
                f"SetupEvidence setup_match must be one of {_VALID_MATCH}, "
                f"got {self.setup_match!r}"
            )
        if not isinstance(self.rs_freshness, Freshness):
            raise ValueError(
                f"SetupEvidence rs_freshness must be a Freshness instance, "
                f"got {self.rs_freshness!r}"
            )
        if not isinstance(self.volume_freshness, Freshness):
            raise ValueError(
                f"SetupEvidence volume_freshness must be a Freshness instance, "
                f"got {self.volume_freshness!r}"
            )
        if self.bb_width_pctile is not None and not (0.0 <= self.bb_width_pctile <= 1.0):
            raise ValueError(
                f"SetupEvidence bb_width_pctile must be 0.0–1.0, "
                f"got {self.bb_width_pctile}"
            )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "setup_name": self.setup_name,
            "setup_match": self.setup_match,
            "match_strength": self.match_strength,
            "failed_gates": list(self.failed_gates),
            "trend": self.trend,
            "rsi": self.rsi,
            "bb_width_pctile": self.bb_width_pctile,
            "vwap_discount_pct": self.vwap_discount_pct,
            "vwap_pct": self.vwap_pct,
            "rs_vs_ihsg_5d": self.rs_vs_ihsg_5d,
            "rs_freshness": self.rs_freshness.value,
            "volume_trend_ratio": self.volume_trend_ratio,
            "volume_freshness": self.volume_freshness.value,
            "candle_source": self.candle_source,
        }
