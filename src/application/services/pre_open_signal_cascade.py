"""Pre-open v1 ordinal signal cascade (ADR-048).

Auction is primary. open_viability is veto-only (does not boost score).
No production signal without auction_ncp or when auction score < auction_min.
MISSING viability ⇒ score on auction alone and cap strength at MODERATE.

Champion rendering is cascade (default). Composite path is separate and must
not run in parallel in production config.

Layer: Application
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.domain.value_objects.decision_constraints import DecisionConstraints
from src.domain.value_objects.pre_open_signal_evidence import (
    PRE_OPEN_SETUP_FAMILY,
    AuctionNcpEvidence,
    OpenViabilityEvidence,
    PreOpenSignalEvidenceBundle,
)
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)


def score_auction_ncp(auction: AuctionNcpEvidence) -> int:
    """Deterministic 0–100 auction quality from NCP-linked fields."""
    score = 55.0  # baseline when IEV+prev_close present

    # Gap: prefer moderate absolute gap (interest without explosion)
    if auction.gap_pct is not None:
        ag = abs(float(auction.gap_pct))
        if ag <= 1.0:
            score += 20.0
        elif ag <= 2.5:
            score += 12.0
        elif ag <= 5.0:
            score += 4.0
        else:
            score -= 15.0
    else:
        score -= 5.0  # missing gap (e.g. fast mode) reduces confidence

    if auction.bid_pressure is not None:
        if auction.bid_pressure >= 0.6:
            score += 15.0
        elif auction.bid_pressure >= 0.45:
            score += 8.0
        elif auction.bid_pressure < 0.35:
            score -= 12.0

    if auction.spread_pct is not None:
        sp = float(auction.spread_pct)
        if sp <= 0.5:
            score += 10.0
        elif sp <= 1.0:
            score += 4.0
        elif sp > 2.0:
            score -= 10.0

    # Mild IEV scale (log-ish without math import): larger interest, modest bump
    if auction.iev >= 500_000:
        score += 8.0
    elif auction.iev >= 200_000:
        score += 4.0

    return int(max(0, min(100, round(score))))


def _strength_from_score(score: int, *, cfg: PreOpenSignalConfig) -> SignalStrength:
    if score >= cfg.strong_min:
        return SignalStrength.STRONG
    if score >= cfg.moderate_min:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK


def _entry_quality(strength: SignalStrength) -> EntryQuality:
    if strength is SignalStrength.STRONG:
        return EntryQuality.ENTER
    if strength is SignalStrength.MODERATE:
        return EntryQuality.WATCH
    return EntryQuality.AVOID


def _cap_entry_quality(
    quality: EntryQuality, max_quality: EntryQuality
) -> EntryQuality:
    order = (EntryQuality.AVOID, EntryQuality.WATCH, EntryQuality.ENTER)
    return order[min(order.index(quality), order.index(max_quality))]


def evaluate_pre_open_signal_cascade(
    bundle: PreOpenSignalEvidenceBundle,
    *,
    snapshot_date: date,
    config: PreOpenSignalConfig | None = None,
) -> AssessSignalResponse | None:
    """Evaluate pre-open signal via v1 cascade. None ⇒ no production signal."""
    cfg = config or PreOpenSignalConfig()
    if cfg.rendering != "cascade":
        raise ValueError(
            "evaluate_pre_open_signal_cascade requires rendering='cascade'; "
            f"got {cfg.rendering!r}"
        )

    auction = bundle.auction_ncp
    if auction is None:
        return None

    auction_score = score_auction_ncp(auction)
    if auction_score < cfg.auction_min:
        return None

    viability = bundle.open_viability
    viability_missing = viability is None

    strength = _strength_from_score(auction_score, cfg=cfg)
    if viability_missing and strength is SignalStrength.STRONG:
        strength = SignalStrength.MODERATE

    entry_quality = _entry_quality(strength)
    reasons: list[str] = [f"auction_score={auction_score}"]
    constraint_reasons: list[str] = []
    max_decision = entry_quality.value

    if viability is not None:
        if viability.gap_out:
            entry_quality = _cap_entry_quality(entry_quality, EntryQuality.AVOID)
            max_decision = "AVOID"
            constraint_reasons.append("viability_veto:gap_out")
            reasons.append("veto:gap_out")
        if viability.friction_fail:
            entry_quality = _cap_entry_quality(entry_quality, EntryQuality.WATCH)
            if max_decision == "ENTER":
                max_decision = "WATCH"
            constraint_reasons.append("viability_veto:friction")
            reasons.append("veto:friction")
        if viability.rsi_extension:
            entry_quality = _cap_entry_quality(entry_quality, EntryQuality.WATCH)
            if max_decision == "ENTER":
                max_decision = "WATCH"
            constraint_reasons.append("viability_veto:rsi_extension")
            reasons.append("veto:rsi_extension")
        if viability.unusual_volume:
            # Caution flag — cap ENTER to WATCH
            entry_quality = _cap_entry_quality(entry_quality, EntryQuality.WATCH)
            if max_decision == "ENTER":
                max_decision = "WATCH"
            constraint_reasons.append("viability_veto:unusual_volume")
            reasons.append("flag:unusual_volume")
    else:
        reasons.append("viability_missing:cap_MODERATE")

    # Re-sync strength if veto forced AVOID from strong auction
    if entry_quality is EntryQuality.AVOID:
        strength = SignalStrength.WEAK
    elif entry_quality is EntryQuality.WATCH and strength is SignalStrength.STRONG:
        strength = SignalStrength.MODERATE

    coverage = 1.0 if not viability_missing else 0.5

    constraints = None
    if constraint_reasons or viability_missing:
        constraints = DecisionConstraints(
            max_decision=max_decision,
            regime=None,
            regime_enter_allowed=True,
            regime_size_multiplier=1.0,
            setup_family=PRE_OPEN_SETUP_FAMILY,
            setup_regime_action=None,
            effective_size_multiplier=1.0,
            constraint_reasons=tuple(constraint_reasons)
            + (("viability_missing",) if viability_missing else ()),
        )

    breakdown: list[tuple[str, float]] = [("auction_ncp", float(auction_score))]
    if viability is not None:
        # Veto-only: record 0 or 100 as presence diagnostic, not a boost
        vetoed = (
            viability.gap_out
            or viability.friction_fail
            or viability.rsi_extension
            or viability.unusual_volume
        )
        breakdown.append(("open_viability_veto", 0.0 if vetoed else 100.0))

    assessment = SignalAssessment(
        ticker=auction.ticker,
        score=auction_score,
        strength=strength,
        entry_quality=entry_quality,
        breakdown=tuple(breakdown),
        rationale=tuple(reasons),
        snapshot_date=snapshot_date,
        signal_authority_coverage=coverage,
        decision_constraints=constraints,
        raw_exact_score=float(auction_score),
    )
    return AssessSignalResponse(
        ticker=auction.ticker,
        assessment=assessment,
        signal_score_raw=auction_score,
        signal_authority_coverage=coverage,
    )


class PreOpenSignalInputsBuilder:
    """Build pre-open evidence and evaluate cascade (scenario seam adapter).

    Does not use SignalEngine setup/flow path; produces AssessSignalResponse
    for TradeSetup composition (ADR-026) via the shared assessment policy.
    """

    def __init__(self, config: PreOpenSignalConfig | None = None) -> None:
        self._config = config or PreOpenSignalConfig()

    @property
    def config(self) -> PreOpenSignalConfig:
        return self._config

    def build_bundle(
        self,
        candidate: object,
        *,
        trade_date: date,
        decision_at=None,
        capture_phase: str = "UNKNOWN",
        snapshot_ref: str | None = None,
    ) -> PreOpenSignalEvidenceBundle:
        from src.application.services.pre_open_signal_evidence_builder import (
            build_pre_open_signal_evidence,
        )

        return build_pre_open_signal_evidence(
            candidate,
            trade_date=trade_date,
            decision_at=decision_at,
            capture_phase=capture_phase,
            snapshot_ref=snapshot_ref,
            config=self._config,
        )

    def evaluate(
        self,
        candidate: object,
        *,
        trade_date: date,
        decision_at=None,
        capture_phase: str = "UNKNOWN",
        snapshot_ref: str | None = None,
    ) -> AssessSignalResponse | None:
        bundle = self.build_bundle(
            candidate,
            trade_date=trade_date,
            decision_at=decision_at,
            capture_phase=capture_phase,
            snapshot_ref=snapshot_ref,
        )
        return evaluate_pre_open_signal_cascade(
            bundle, snapshot_date=trade_date, config=self._config
        )
