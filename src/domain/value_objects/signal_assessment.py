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

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
    from src.domain.value_objects.decision_constraints import DecisionConstraints


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

    # ── Insider activity ──────────────────────────────────────────────────────
    # Net insider buy direction: -1.0 (full selling) → 0.0 (neutral) → +1.0 (full buying).
    # None until an insider data provider is wired; gracefully defaults to neutral 50.0.
    # Replaces piotroski_f_score which belonged in GateContext (RiskEngine path only).
    insider_net_buy_ratio: float | None = None  # -1.0 to +1.0

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

    seasonality_total_years: int | None = None
    # Threaded from SeasonalEdge.total_years in signal_context_builder.py.
    # Required by Phase 6 sample guard (< 5 years → evidence unavailable).
    seasonality_back_years: int | None = None
    # Threaded from SeasonalEdge.back_years — the lookback window requested
    # when fetching (e.g. 5). Preserved in raw_fields for policy replay.


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
    # HIGH-2 canonical name: production-authority coverage (0.0-1.0), or None
    # if not evaluated (e.g., in the archived six-factor scorer). Not
    # statistical confidence or trade conviction — see
    # SignalEvidenceGroupScorer._compute_signal_authority_coverage.
    signal_authority_coverage: float | None
    decision_constraints: "DecisionConstraints | None" = None
    legacy_conditioned_score: int | None = None
    raw_exact_score: float | None = None
    alpha_trigger_score: "AlphaTriggerScore | None" = None

    def __post_init__(self) -> None:
        if not (0 <= self.score <= 100):
            raise ValueError(f"SignalAssessment score must be 0–100, got {self.score}")
        if self.legacy_conditioned_score is not None and not (0 <= self.legacy_conditioned_score <= 100):
            raise ValueError(
                f"SignalAssessment legacy_conditioned_score must be 0–100, "
                f"got {self.legacy_conditioned_score}"
            )
        if (
            self.signal_authority_coverage is not None
            and not 0.0 <= self.signal_authority_coverage <= 1.0
        ):
            raise ValueError(
                f"SignalAssessment signal_authority_coverage must be 0.0–1.0, "
                f"got {self.signal_authority_coverage}"
            )
        if self.raw_exact_score is not None and not (0.0 <= self.raw_exact_score <= 100.0):
            raise ValueError(
                f"SignalAssessment raw_exact_score must be 0.0–100.0, "
                f"got {self.raw_exact_score}"
            )

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
            "legacy_conditioned_score": self.legacy_conditioned_score,
            "strength": self.strength.value,
            "entry_quality": self.entry_quality.value,
            "breakdown": self.breakdown_dict,
            "rationale": list(self.rationale),
            "snapshot_date": self.snapshot_date.isoformat(),
            "signal_authority_coverage": self.signal_authority_coverage,
            "raw_exact_score": self.raw_exact_score,
            "alpha_trigger_score": (
                self.alpha_trigger_score.to_dict()
                if self.alpha_trigger_score else None
            ),
            "decision_constraints": (
                self.decision_constraints.to_dict()
                if self.decision_constraints else None
            ),
        }
