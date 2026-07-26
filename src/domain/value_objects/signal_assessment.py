"""
Signal assessment value objects.

Defines the output contract for the SignalEngine: enums, SignalContext (pre-loaded
input data), and SignalAssessment (immutable result).

Mirrors the risk assessment layer structurally (pre-loaded input bundle + result):
  GateContext      → SignalContext    (structural parallel only — SignalContext is
                                        non-authoritative enrichment, NOT the
                                        weighted-score source; that is
                                        CanonicalSignalEvidenceInput)
  RiskAssessment   → SignalAssessment
  (risk has no RiskLevel/Profile enum — display-only OPEN/BLOCKED verdict via
   RiskAssessment.risk_level_name; signal classifies via SignalStrength/EntryQuality)

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
    """Signal intensity derived by the selected contextual policy."""

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class EntryQuality(Enum):
    """Entry recommendation derived from signal strength."""

    ENTER = "ENTER"
    WATCH = "WATCH"
    AVOID = "AVOID"


class SignalAssessmentPurpose(Enum):
    """Workflow purpose governed by one explicit signal policy contract."""

    PRE_OPEN_AUCTION_DIRECTION = "PRE_OPEN_AUCTION_DIRECTION"
    ACCUMULATION_DISCOVERY = "ACCUMULATION_DISCOVERY"
    SWING_TRADE_SETUP = "SWING_TRADE_SETUP"


_POLICY_CONTRACT_BY_PURPOSE = {
    SignalAssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION: "pre_open_auction_direction.v1",
    SignalAssessmentPurpose.ACCUMULATION_DISCOVERY: "accumulation_discovery.v1",
    SignalAssessmentPurpose.SWING_TRADE_SETUP: "swing_trade_setup.v1",
}


@dataclass(frozen=True)
class SignalAssessmentIdentity:
    """Fail-closed binding between workflow purpose and scoring policy."""

    purpose: SignalAssessmentPurpose
    policy_contract: str

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, SignalAssessmentPurpose):
            raise ValueError(f"Unknown signal assessment purpose: {self.purpose!r}")
        expected = _POLICY_CONTRACT_BY_PURPOSE[self.purpose]
        if self.policy_contract != expected:
            raise ValueError(
                "Signal assessment policy contract mismatch: "
                f"{self.purpose.value} requires {expected!r}, "
                f"got {self.policy_contract!r}"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "purpose": self.purpose.value,
            "policy_contract": self.policy_contract,
        }


PRE_OPEN_AUCTION_DIRECTION_IDENTITY = SignalAssessmentIdentity(
    purpose=SignalAssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
    policy_contract="pre_open_auction_direction.v1",
)
ACCUMULATION_DISCOVERY_IDENTITY = SignalAssessmentIdentity(
    purpose=SignalAssessmentPurpose.ACCUMULATION_DISCOVERY,
    policy_contract="accumulation_discovery.v1",
)
SWING_TRADE_SETUP_IDENTITY = SignalAssessmentIdentity(
    purpose=SignalAssessmentPurpose.SWING_TRADE_SETUP,
    policy_contract="swing_trade_setup.v1",
)


@dataclass(frozen=True)
class SignalContext:
    """
    Pre-loaded, non-authoritative enrichment inputs for signal evaluation.

    NOT the source of the setup/flow evidence score. That score is produced from
    the Setup + Flow evidence groups carried by CanonicalSignalEvidenceInput
    (see AssessSignalEvidenceUseCase / SignalEvidenceGroupScorer). The fields
    here are consumed only as non-authoritative side inputs:
      - penalty flags — SignalEvidenceGroupScorer._evaluate_flags reads
        forward_pe / analyst_buy_pct / insider_net_buy_ratio to apply
        "do-no-harm" score penalties (never a positive contribution);
      - company-quality sub-scores — company_quality_scoring /
        company_quality_context_evidence_builder;
      - factor-presence checks — signal_presence.

    The application layer (SignalEngine._build_signal_context) populates this
    from provider calls. The use case receives only plain Python values — no
    providers, no IO, no lazy loading.

    Structurally parallel to GateContext (domain/rules/risk_gate.py) as a
    pre-loaded input bundle, but asymmetric in authority: GateContext drives
    risk-gate decisions, whereas SignalContext never drives the weighted signal
    score.

    For screener loops, callers build this once per candidate from pre-loaded
    data and pass it via the purpose-specific SignalEngine method to avoid N+1
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
    # Consumed as a penalty flag (INSIDER_SELLING when below threshold) and by
    # company-quality scoring; None means it is simply not evaluated (no
    # neutral-fill). Lives here, not in GateContext (that is the RiskEngine path).
    insider_net_buy_ratio: float | None = None  # -1.0 to +1.0

    # ── Seasonality (monthly, from SeasonalEdge) ──────────────────────────────
    # Feeds seasonality factor-presence (signal_presence) and company-quality
    # context — NOT the weighted Setup/Flow score. win_rate_pct is the primary
    # value; avg_return_pct gives tailwind/headwind/neutral direction.
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

    Produced by AssessSignalEvidenceUseCase and consumed by CLI display, screeners,
    and CombinedAssessment composition (ADR-026).

    breakdown uses tuple-of-tuples (not dict) so the frozen dataclass remains
    hashable. Use breakdown_dict property for dict access.
    """

    identity: SignalAssessmentIdentity
    ticker: str
    score: int                              # 0–100 contextual policy score
    strength: SignalStrength                # STRONG / MODERATE / WEAK
    entry_quality: EntryQuality            # ENTER / WATCH / AVOID
    breakdown: tuple[tuple[str, float], ...] # (factor_name, component_score) pairs
    rationale: tuple[str, ...]
    snapshot_date: date
    # HIGH-2 canonical name: production-authority coverage (0.0-1.0), or None
    # if not yet evaluated for this assessment. Not statistical confidence or
    # trade conviction — see SignalEvidenceGroupScorer._compute_signal_authority_coverage.
    signal_authority_coverage: float | None
    decision_constraints: "DecisionConstraints | None" = None
    legacy_conditioned_score: int | None = None
    raw_exact_score: float | None = None
    alpha_trigger_score: "AlphaTriggerScore | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SignalAssessmentIdentity):
            raise ValueError("SignalAssessment identity is required")
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
            "identity": self.identity.to_dict(),
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
