"""
SignalEvidenceGroupScorer — handles setup/flow scoring, renormalization, flags, and classification.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalStrength,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalEvidenceRequest
    from src.application.services.signal_engine_config import SignalEngineConfig
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.signal_assessment import SignalContext


@dataclass(frozen=True)
class SignalEvidenceGroupScores:
    setup_score: float
    setup_present: bool
    flow_score: float
    flow_present: bool
    base_score: float
    confidence: float
    active_flags: tuple[str, ...]
    flag_adjustment: int
    raw_exact_score: float
    raw_group_score: int
    final_score: int
    strength: SignalStrength
    entry_quality: EntryQuality
    gate_tightened: bool
    coverage_warning: str | None


class SignalEvidenceGroupScorer:
    @staticmethod
    def score(
        request: AssessSignalEvidenceRequest,
        config: SignalEngineConfig,
    ) -> SignalEvidenceGroupScores:
        setup_score, setup_present = SignalEvidenceGroupScorer._score_setup_group(
            request.setup_evidence
        )
        flow_score, flow_present = SignalEvidenceGroupScorer._score_flow_group(
            request.flow_confirmation_evidence
        )

        base_score, confidence = SignalEvidenceGroupScorer.renormalize(
            setup_score, setup_present, flow_score, flow_present, config
        )

        active_flags, flag_adjustment = SignalEvidenceGroupScorer._evaluate_flags(
            request.signal_context, config
        )

        raw_exact_score = max(0.0, min(100.0, base_score + flag_adjustment))
        raw_group_score = round(base_score)
        final_score = max(0, min(100, raw_group_score + flag_adjustment))

        strength = SignalEvidenceGroupScorer._classify_strength(final_score, config)
        entry_quality = SignalEvidenceGroupScorer._classify_entry(strength, confidence, config)

        entry_quality, gate_tightened = SignalEvidenceGroupScorer._apply_gate_tightening(
            entry_quality, request.market_context
        )

        coverage_warning = SignalEvidenceGroupScorer._coverage_warning(
            confidence, setup_present, flow_present
        )

        return SignalEvidenceGroupScores(
            setup_score=setup_score,
            setup_present=setup_present,
            flow_score=flow_score,
            flow_present=flow_present,
            base_score=base_score,
            confidence=confidence,
            active_flags=tuple(active_flags),
            flag_adjustment=flag_adjustment,
            raw_exact_score=raw_exact_score,
            raw_group_score=raw_group_score,
            final_score=final_score,
            strength=strength,
            entry_quality=entry_quality,
            gate_tightened=gate_tightened,
            coverage_warning=coverage_warning,
        )

    @staticmethod
    def _score_setup_group(ev: SetupEvidence | None) -> tuple[float, bool]:
        if ev is None:
            return 0.0, False
        return float(ev.match_strength), True

    @staticmethod
    def _score_flow_group(ev: FlowConfirmationEvidence | None) -> tuple[float, bool]:
        if ev is None:
            return 0.0, False
        return max(0.0, min(100.0, ev.capped_strength * 100.0)), True

    @staticmethod
    def renormalize(
        setup_score: float,
        setup_present: bool,
        flow_score: float,
        flow_present: bool,
        config: SignalEngineConfig,
    ) -> tuple[float, float]:
        """Compute base score and confidence from present evidence groups.

        confidence = present_weight / total_weight.
        When no groups are present, base_score = 50.0 (no directional information).
        """
        g = config.evidence_groups
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

    @staticmethod
    def _evaluate_flags(
        ctx: SignalContext | None,
        config: SignalEngineConfig,
    ) -> tuple[list[str], int]:
        if ctx is None:
            return [], 0

        flags_cfg = config.flags
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

    @staticmethod
    def _classify_strength(score: int, config: SignalEngineConfig) -> SignalStrength:
        cfg = config.classification
        if score >= cfg.strong_min_score:
            return SignalStrength.STRONG
        if score >= cfg.moderate_min_score:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    @staticmethod
    def _classify_entry(
        strength: SignalStrength, confidence: float, config: SignalEngineConfig
    ) -> EntryQuality:
        cfg = config.classification
        if strength == SignalStrength.STRONG and confidence >= cfg.enter_min_confidence:
            return EntryQuality.ENTER
        if (
            strength in {SignalStrength.STRONG, SignalStrength.MODERATE}
            and confidence >= cfg.watch_min_confidence
        ):
            return EntryQuality.WATCH
        return EntryQuality.AVOID

    @staticmethod
    def _apply_gate_tightening(
        entry_quality: EntryQuality,
        market_context: MarketContext | None,
    ) -> tuple[EntryQuality, bool]:
        if (
            market_context is not None
            and market_context.gate_tightening
            and entry_quality == EntryQuality.ENTER
        ):
            return EntryQuality.WATCH, True
        return entry_quality, False

    @staticmethod
    def _coverage_warning(
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
