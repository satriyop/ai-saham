"""
SignalLegacyRegimeConditioning — legacy regime diagnostics.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScorer

if TYPE_CHECKING:
    from src.application.services.signal_engine_config import SignalEngineConfig
    from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class LegacyRegimeConditioningResult:
    setup_score: float
    flow_score: float
    notes: tuple[str, ...]
    legacy_conditioned_score: int


class SignalLegacyRegimeConditioning:
    @staticmethod
    def condition(
        setup_score: float,
        setup_present: bool,
        flow_score: float,
        flow_present: bool,
        market_context: MarketContext | None,
        config: SignalEngineConfig,
        flag_adjustment: int,
    ) -> LegacyRegimeConditioningResult:
        setup_score_conditioned, flow_score_conditioned, regime_notes = (
            SignalLegacyRegimeConditioning._condition_group_scores(
                setup_score,
                setup_present,
                flow_score,
                flow_present,
                market_context,
                config,
            )
        )

        base_score_conditioned, _ = SignalEvidenceGroupScorer.renormalize(
            setup_score_conditioned,
            setup_present,
            flow_score_conditioned,
            flow_present,
            config,
        )

        legacy_conditioned_score = max(0, min(100, round(base_score_conditioned) + flag_adjustment))

        return LegacyRegimeConditioningResult(
            setup_score=setup_score_conditioned,
            flow_score=flow_score_conditioned,
            notes=tuple(regime_notes),
            legacy_conditioned_score=legacy_conditioned_score,
        )

    @staticmethod
    def _condition_group_scores(
        setup_score: float,
        setup_present: bool,
        flow_score: float,
        flow_present: bool,
        market_context: MarketContext | None,
        config: SignalEngineConfig,
    ) -> tuple[float, float, list[str]]:
        if market_context is None:
            return setup_score, flow_score, []

        regime = market_context.regime.value
        cfg = config.regime_conditioning
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
                    f"VOLATILE: setup {old_s:.0f}→{setup_score:.0f} (×{rc.setup_discount:.2f})"
                )
            if flow_present:
                old_f = flow_score
                flow_score = flow_score * rc.flow_discount
                notes.append(
                    f"VOLATILE: flow {old_f:.0f}→{flow_score:.0f} (×{rc.flow_discount:.2f})"
                )

        return setup_score, flow_score, notes
