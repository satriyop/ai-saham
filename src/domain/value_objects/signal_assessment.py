"""
Signal assessment value objects.

Defines the output contract for the SignalEngine: enums, SignalContext (pre-loaded
input data), and SignalAssessment (immutable result).

Mirrors the risk assessment layer:
  GateContext      → SignalContext
  RiskAssessment   → SignalAssessment
  RiskLevel/Profile → SignalStrength/EntryQuality

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class SignalStrength(Enum):
    """Composite signal intensity derived from the weighted score."""

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class EntryQuality(Enum):
    """Entry recommendation derived from signal strength."""

    ENTER = "ENTER"
    WATCH = "WATCH"
    AVOID = "AVOID"


@dataclass(frozen=True)
class SignalContext:
    """
    Pre-loaded enrichment data passed to AssessSignalUseCase.

    The application layer (SignalEngine._build_signal_context) is responsible
    for populating this from provider calls. The use case receives only plain
    Python values — no providers, no IO, no lazy loading.

    Parallel to GateContext in domain/rules/risk_gate.py.

    For screener loops, callers build this once per candidate from pre-loaded
    data and pass it via SignalEngine.evaluate_with_context() to avoid N+1
    provider fetches.
    """

    ticker: str
    snapshot_date: date

    # ── Bandar detector (daily, from BandarDetectorSnapshot) ─────────────────
    # broad_score is a sum of intensity slots; its range depends on how many
    # optional accdist fields (top3/top5/top10) were populated.
    # bandar_max_range = (3 + num_optional) * 2  (6 base, up to 12 with all optional)
    bandar_broad_score: int | None = None
    bandar_max_range: int = 6  # default: only today + five_day + top1 present

    # ── Foreign flow quality (screener path only) ─────────────────────────────
    # Pre-computed by AccumulationScreenUseCase; None in self-fetch path.
    foreign_flow_quality: float | None = None   # 0.0–1.0

    # ── Fundamental quality (quarterly, from CompanyFundamentals) ─────────────
    piotroski_f_score: int | None = None        # 0–9

    # ── Seasonality (monthly, from SeasonalEdge) ──────────────────────────────
    # Both fields needed: win_rate_pct drives the score;
    # avg_return_pct determines tailwind/headwind/neutral direction.
    seasonality_win_rate: float | None = None       # 0.0–100.0
    seasonality_avg_return_pct: float | None = None # e.g. +2.1 = +2.1%, -1.0 = -1.0%

    # ── Analyst consensus (daily, from AnalystConsensus) ─────────────────────
    analyst_buy_pct: float | None = None        # 0.0–1.0  (buy_count / analyst_count)
    analyst_upside_pct: float | None = None     # percentage, e.g. 15.0 = 15% upside

    # ── Forward valuation (daily, from ForwardEstimates.forward_pe) ──────────
    # Pre-computed by ForwardEstimates.compute(). None for loss-making companies.
    forward_pe: float | None = None


@dataclass(frozen=True)
class SignalAssessment:
    """
    Immutable result of signal evaluation.

    Produced by AssessSignalUseCase and consumed by CLI display, screeners,
    and CombinedAssessment composition (ADR-026).

    breakdown uses tuple-of-tuples (not dict) so the frozen dataclass remains
    hashable. Use breakdown_dict property for dict access.
    """

    ticker: str
    score: int                              # 0–100 final weighted composite
    strength: SignalStrength                # STRONG / MODERATE / WEAK
    entry_quality: EntryQuality            # ENTER / WATCH / AVOID
    breakdown: tuple[tuple[str, float], ...] # (factor_name, component_score) pairs
    rationale: tuple[str, ...]
    snapshot_date: date

    def __post_init__(self) -> None:
        if not (0 <= self.score <= 100):
            raise ValueError(f"SignalAssessment score must be 0–100, got {self.score}")

    @property
    def breakdown_dict(self) -> dict[str, float]:
        """Convenience accessor returning breakdown as a plain dict."""
        return dict(self.breakdown)

    @property
    def score_label(self) -> str:
        """Compact display label, e.g. '72★' for STRONG or '55·' otherwise."""
        star = "★" if self.strength == SignalStrength.STRONG else "·"
        return f"{self.score}{star}"

    @property
    def strength_label(self) -> str:
        return self.strength.value

    @property
    def entry_quality_label(self) -> str:
        return self.entry_quality.value

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "score": self.score,
            "strength": self.strength.value,
            "entry_quality": self.entry_quality.value,
            "breakdown": self.breakdown_dict,
            "rationale": list(self.rationale),
            "snapshot_date": self.snapshot_date.isoformat(),
        }
