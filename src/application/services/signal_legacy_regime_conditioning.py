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
    flow_group_score: float
    notes: tuple[str, ...]
    legacy_conditioned_score: int


class SignalLegacyRegimeConditioning:
    """Diagnostic-only regime conditioning over the flow confirmation group.

    ADR-067 retired ``setup_quality`` as an evidence group, and with it the two
    branches that conditioned a setup group score (RISK_OFF's weak-setup
    discount and VOLATILE's setup half). Neither could reach any score once the
    two-name blend was deleted, so this service now conditions flow alone.
    """

    @staticmethod
    def condition(
        flow_group_score: float,
        flow_present: bool,
        market_context: MarketContext | None,
        config: SignalEngineConfig,
        flag_adjustment: int,
    ) -> LegacyRegimeConditioningResult:
        flow_score_conditioned, regime_notes = (
            SignalLegacyRegimeConditioning._condition_group_scores(
                flow_group_score,
                flow_present,
                market_context,
                config,
            )
        )

        base_score_conditioned = SignalEvidenceGroupScorer.base_score_from_flow_group(
            flow_score_conditioned,
            flow_present,
        )

        legacy_conditioned_score = max(0, min(100, round(base_score_conditioned) + flag_adjustment))

        return LegacyRegimeConditioningResult(
            flow_group_score=flow_score_conditioned,
            notes=tuple(regime_notes),
            legacy_conditioned_score=legacy_conditioned_score,
        )

    @staticmethod
    def _condition_group_scores(
        flow_group_score: float,
        flow_present: bool,
        market_context: MarketContext | None,
        config: SignalEngineConfig,
    ) -> tuple[float, list[str]]:
        if market_context is None:
            return flow_group_score, []

        regime = market_context.regime.value
        cfg = config.regime_conditioning
        notes: list[str] = []

        if regime == "NEUTRAL" and flow_present:
            rc = cfg.neutral
            if flow_group_score < rc.weak_flow_threshold:
                old = flow_group_score
                flow_group_score = flow_group_score * rc.weak_flow_discount
                notes.append(
                    f"NEUTRAL: flow {old:.0f}→{flow_group_score:.0f} "
                    f"(×{rc.weak_flow_discount:.2f}, below confirmation threshold)"
                )

        elif regime == "VOLATILE" and flow_present:
            rc = cfg.volatile
            old_f = flow_group_score
            flow_group_score = flow_group_score * rc.flow_discount
            notes.append(
                f"VOLATILE: flow {old_f:.0f}→{flow_group_score:.0f} (×{rc.flow_discount:.2f})"
            )

        return flow_group_score, notes
