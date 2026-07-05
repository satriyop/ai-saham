"""
AssessSignalEvidenceUseCase — staged evidence-first signal aggregator (Phase 4/5).

Phase 4: two-group staged aggregation replaces flat 6-factor weighted average.
  Group 1 — Setup Quality     (default weight 0.60)
  Group 2 — Flow Confirmation (default weight 0.40)

Phase 5: regime-conditional group score conditioning applied before renormalization.
  RISK_ON:   no conditioning (normal confidence).
  NEUTRAL:   weak flow confirmation discounted.
  RISK_OFF:  weak setup evidence (non-MATCH) discounted.
  VOLATILE:  both groups discounted.
  gate_tightening: ENTER → WATCH cap applied after classification.

Missing evidence excluded from weight denominator. Flags from SignalContext apply
score penalties as do-no-harm signals.

Layer: Application
Depends on: domain only + stdlib. No IO, no providers, no repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from src.application.use_case.assess_signal_use_case import (
    AssessSignalResponse,
    SignalEngineConfig,
)
from src.application.services.decision_policy import DecisionPolicyService
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalContext,
    SignalStrength,
)

if TYPE_CHECKING:
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.setup_evidence import SetupEvidence


@dataclass
class AssessSignalEvidenceRequest:
    ticker: str
    snapshot_date: date
    setup_evidence: "SetupEvidence | None" = None
    flow_confirmation_evidence: "FlowConfirmationEvidence | None" = None
    signal_context: SignalContext | None = None   # for flag evaluation
    market_context: "MarketContext | None" = None  # for regime conditioning
    setup_family: str | None = None


class AssessSignalEvidenceUseCase:
    """
    Staged evidence-first signal aggregator.

    Two evidence groups contribute directional votes; flags from SignalContext
    apply score penalties for fundamental risk signals. Missing evidence lowers
    confidence but does not fabricate a neutral direction.
    """

    def __init__(self, config: SignalEngineConfig | None = None) -> None:
        self._config = config or SignalEngineConfig()

    def execute(self, request: AssessSignalEvidenceRequest) -> AssessSignalResponse:
        # ── Stage 1: Group scoring ────────────────────────────────────────────
        setup_score, setup_present = self._score_setup_group(request.setup_evidence)
        flow_score, flow_present = self._score_flow_group(request.flow_confirmation_evidence)

        # Save regime-neutral group scores before conditioning (for comparability)
        setup_score_raw, flow_score_raw = setup_score, flow_score

        # ── Stage 2: Regime conditioning (before renormalization) ─────────────
        setup_score, flow_score, regime_notes = self._condition_group_scores(
            setup_score, setup_present, flow_score, flow_present, request.market_context
        )

        # ── Stage 3: Renormalize — missing groups excluded from denominator ───
        base_score, confidence = self._renormalize(
            setup_score, setup_present, flow_score, flow_present
        )

        # ── Stage 4: Flags (do-no-harm penalties from SignalContext) ──────────
        active_flags, flag_adj = self._evaluate_flags(request.signal_context)

        # ── Final score (regime-conditioned) ─────────────────────────────────
        raw_group_score = round(base_score)
        final_score = max(0, min(100, raw_group_score + flag_adj))

        # Pre-regime score: regime-neutral groups → renormalize → flags
        # Preserved separately so score comparability holds across regime changes.
        base_score_neutral, _ = self._renormalize(
            setup_score_raw, setup_present, flow_score_raw, flow_present
        )
        signal_score_raw = max(0, min(100, round(base_score_neutral) + flag_adj))

        strength = self._classify_strength(final_score)
        entry_quality = self._classify_entry(strength, confidence)

        # ── Stage 5: Gate tightening (ENTER → WATCH cap) ─────────────────────
        entry_quality, gate_tightened = self._apply_gate_tightening(
            entry_quality, request.market_context
        )

        # ── Stage 6: Decision constraints (A1 explicit policy) ───────────────
        decision_result = DecisionPolicyService(self._config.decision_policy).resolve(
            entry_quality=entry_quality,
            score=final_score,
            coverage_score=confidence,
            conviction_score=confidence,
            market_context=request.market_context,
            setup_family=request.setup_family,
        )
        entry_quality = decision_result.entry_quality
        decision_constraints = decision_result.constraints

        breakdown = self._build_breakdown(
            setup_score, setup_present, flow_score, flow_present,
            confidence, active_flags, flag_adj, bool(regime_notes), gate_tightened,
        )
        rationale = self._build_rationale(
            request.ticker, final_score, strength, entry_quality,
            setup_present, flow_present, confidence, active_flags, flag_adj,
            regime_notes, gate_tightened,
        )

        assessment = SignalAssessment(
            ticker=request.ticker,
            score=final_score,
            strength=strength,
            entry_quality=entry_quality,
            breakdown=breakdown,
            rationale=rationale,
            snapshot_date=request.snapshot_date,
            confidence_score=round(confidence, 4),
            decision_constraints=decision_constraints,
        )

        coverage_warning = self._coverage_warning(confidence, setup_present, flow_present)

        return AssessSignalResponse(
            ticker=request.ticker,
            assessment=assessment,
            coverage_warning=coverage_warning,
            evidence_confidence=round(confidence, 4),
            active_flags=tuple(active_flags),
            flag_adjustment=flag_adj,
            raw_group_score=raw_group_score,
            signal_score_raw=signal_score_raw,
        )

    # ── group scorers ─────────────────────────────────────────────────────────

    def _score_setup_group(self, ev: "SetupEvidence | None") -> tuple[float, bool]:
        """Setup quality group score (0–100) from SetupEvidence.match_strength."""
        if ev is None:
            return 0.0, False
        return float(ev.match_strength), True

    def _score_flow_group(self, ev: "FlowConfirmationEvidence | None") -> tuple[float, bool]:
        """Flow confirmation group score (0–100) from capped_strength (0–1)."""
        if ev is None:
            return 0.0, False
        return max(0.0, min(100.0, ev.capped_strength * 100.0)), True

    # ── regime conditioning ───────────────────────────────────────────────────

    def _condition_group_scores(
        self,
        setup_score: float, setup_present: bool,
        flow_score: float, flow_present: bool,
        market_context: "MarketContext | None",
    ) -> tuple[float, float, list[str]]:
        """Apply regime-specific conditioning to group scores before renormalization.

        Returns (conditioned_setup_score, conditioned_flow_score, regime_notes).
        RISK_ON: no change. Notes list is empty when no conditioning fires.
        """
        if market_context is None:
            return setup_score, flow_score, []

        regime = market_context.regime.value
        cfg = self._config.regime_conditioning
        notes: list[str] = []

        if regime == "RISK_OFF" and setup_present:
            rc = cfg.risk_off
            if setup_score < rc.weak_setup_threshold:
                old = setup_score
                setup_score = setup_score * rc.weak_setup_discount
                notes.append(
                    f"RISK_OFF: setup {old:.0f}→{setup_score:.0f} "
                    f"(×{rc.weak_setup_discount:.2f}, below MATCH threshold)"
                )

        elif regime == "NEUTRAL" and flow_present:
            rc = cfg.neutral
            if flow_score < rc.weak_flow_threshold:
                old = flow_score
                flow_score = flow_score * rc.weak_flow_discount
                notes.append(
                    f"NEUTRAL: flow {old:.0f}→{flow_score:.0f} "
                    f"(×{rc.weak_flow_discount:.2f}, below confirmation threshold)"
                )

        elif regime == "VOLATILE":
            rc = cfg.volatile
            if setup_present:
                old_s = setup_score
                setup_score = setup_score * rc.setup_discount
                notes.append(
                    f"VOLATILE: setup {old_s:.0f}→{setup_score:.0f} "
                    f"(×{rc.setup_discount:.2f})"
                )
            if flow_present:
                old_f = flow_score
                flow_score = flow_score * rc.flow_discount
                notes.append(
                    f"VOLATILE: flow {old_f:.0f}→{flow_score:.0f} "
                    f"(×{rc.flow_discount:.2f})"
                )

        return setup_score, flow_score, notes

    def _apply_gate_tightening(
        self,
        entry_quality: EntryQuality,
        market_context: "MarketContext | None",
    ) -> tuple[EntryQuality, bool]:
        """Cap ENTER→WATCH when gate_tightening is set on market_context."""
        if (
            market_context is not None
            and market_context.gate_tightening
            and entry_quality == EntryQuality.ENTER
        ):
            return EntryQuality.WATCH, True
        return entry_quality, False

    # ── renormalization ───────────────────────────────────────────────────────

    def _renormalize(
        self,
        setup_score: float, setup_present: bool,
        flow_score: float, flow_present: bool,
    ) -> tuple[float, float]:
        """
        Compute base score and confidence from present evidence groups.

        confidence = present_weight / total_weight.
        When no groups are present, base_score = 50.0 (no directional information).
        """
        g = self._config.evidence_groups
        total_weight = g.setup_quality.weight + g.flow_confirmation.weight

        active: list[tuple[float, float]] = []  # (score, weight)
        if setup_present:
            active.append((setup_score, g.setup_quality.weight))
        if flow_present:
            active.append((flow_score, g.flow_confirmation.weight))

        if not active:
            return 50.0, 0.0

        present_weight = sum(w for _, w in active)
        base_score = sum(s * w for s, w in active) / present_weight
        confidence = min(1.0, present_weight / total_weight) if total_weight > 0 else 0.0
        return base_score, confidence

    # ── flags ─────────────────────────────────────────────────────────────────

    def _evaluate_flags(
        self, ctx: SignalContext | None
    ) -> tuple[list[str], int]:
        """Return (active_flag_names, total_penalty) from SignalContext."""
        if ctx is None:
            return [], 0

        flags_cfg = self._config.flags
        active: list[str] = []
        total_penalty = 0

        if (
            flags_cfg.valuation_stretched.enabled
            and ctx.forward_pe is not None
            and ctx.forward_pe > flags_cfg.valuation_stretched.forward_pe_threshold
        ):
            active.append("VALUATION_STRETCHED")
            total_penalty -= flags_cfg.valuation_stretched.score_penalty

        if (
            flags_cfg.analyst_bearish.enabled
            and ctx.analyst_buy_pct is not None
            and ctx.analyst_buy_pct < flags_cfg.analyst_bearish.buy_ratio_threshold
        ):
            active.append("ANALYST_BEARISH")
            total_penalty -= flags_cfg.analyst_bearish.score_penalty

        if (
            flags_cfg.insider_selling.enabled
            and ctx.insider_net_buy_ratio is not None
            and ctx.insider_net_buy_ratio < flags_cfg.insider_selling.net_buy_ratio_threshold
        ):
            active.append("INSIDER_SELLING")
            total_penalty -= flags_cfg.insider_selling.score_penalty

        return active, total_penalty

    # ── breakdown and rationale ───────────────────────────────────────────────

    def _build_breakdown(
        self,
        setup_score: float, setup_present: bool,
        flow_score: float, flow_present: bool,
        confidence: float,
        active_flags: list[str],
        flag_adj: int,
        regime_conditioned: bool,
        gate_tightened: bool,
    ) -> tuple[tuple[str, float], ...]:
        entries: list[tuple[str, float]] = []
        if setup_present:
            entries.append(("setup_quality_group", round(setup_score, 2)))
        if flow_present:
            entries.append(("flow_confirmation_group", round(flow_score, 2)))
        entries.append(("evidence_confidence", round(confidence * 100.0, 2)))
        if flag_adj != 0:
            entries.append(("flag_adjustment", float(flag_adj)))
        if regime_conditioned:
            entries.append(("regime_conditioning", 1.0))
        if gate_tightened:
            entries.append(("gate_tightening", 1.0))
        return tuple(entries)

    def _build_rationale(
        self,
        ticker: str,
        final_score: int,
        strength: SignalStrength,
        entry_quality: EntryQuality,
        setup_present: bool,
        flow_present: bool,
        confidence: float,
        active_flags: list[str],
        flag_adj: int,
        regime_notes: list[str],
        gate_tightened: bool,
    ) -> tuple[str, ...]:
        lines: list[str] = []
        if not setup_present:
            lines.append("Setup quality: no evidence (excluded from score)")
        if not flow_present:
            lines.append("Flow confirmation: no evidence (excluded from score)")
        if active_flags:
            flag_str = ", ".join(active_flags)
            lines.append(f"Flags active: {flag_str} ({flag_adj:+d} pts)")
        for note in regime_notes:
            lines.append(note)
        if gate_tightened:
            lines.append("Gate tightening: ENTER → WATCH (regime gate_tightening=True)")
        lines.append(
            f"Evidence confidence: {confidence:.0%} — "
            f"score {final_score} ({strength.value}/{entry_quality.value})"
        )
        return tuple(lines)

    # ── classification ────────────────────────────────────────────────────────

    def _classify_strength(self, score: int) -> SignalStrength:
        cfg = self._config.classification
        if score >= cfg.strong_min_score:
            return SignalStrength.STRONG
        if score >= cfg.moderate_min_score:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _classify_entry(
        self, strength: SignalStrength, confidence: float
    ) -> EntryQuality:
        cfg = self._config.classification
        if strength == SignalStrength.STRONG and confidence >= cfg.enter_min_confidence:
            return EntryQuality.ENTER
        if (
            strength in {SignalStrength.STRONG, SignalStrength.MODERATE}
            and confidence >= cfg.watch_min_confidence
        ):
            return EntryQuality.WATCH
        return EntryQuality.AVOID

    # ── coverage warning ──────────────────────────────────────────────────────

    def _coverage_warning(
        self,
        confidence: float,
        setup_present: bool,
        flow_present: bool,
    ) -> str | None:
        if confidence == 0.0:
            return "No evidence groups present — score is neutral prior only"
        if confidence < 0.5:
            missing = []
            if not setup_present:
                missing.append("setup_quality")
            if not flow_present:
                missing.append("flow_confirmation")
            return f"Low evidence confidence ({confidence:.0%}) — missing: {', '.join(missing)}"
        return None
