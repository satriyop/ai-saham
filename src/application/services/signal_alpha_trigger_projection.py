"""
SignalAlphaTriggerProjection — handles projection input mapping and trigger aggregation.

Layer: Application
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.alpha_trigger_aggregator import (
    AlphaTriggerAggregationRequest,
    AlphaTriggerAggregator,
    AlphaTriggerGroupInput,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalEvidenceRequest
    from src.application.services.signal_engine_config import SignalEngineConfig
    from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScores
    from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence


class SignalAlphaTriggerProjection:
    @staticmethod
    def build_score(
        request: AssessSignalEvidenceRequest,
        config: SignalEngineConfig,
        group_scores: SignalEvidenceGroupScores,
    ) -> AlphaTriggerScore | None:
        if not config.alpha_trigger.enabled:
            return None

        aggregator = AlphaTriggerAggregator(config.alpha_trigger)

        return aggregator.aggregate(
            AlphaTriggerAggregationRequest(
                horizon=request.horizon or config.alpha_trigger.default_horizon,
                groups=(
                    AlphaTriggerGroupInput(
                        group="setup_quality",
                        score=group_scores.setup_score,
                        configured_weight=config.alpha_trigger.group_weights.get(
                            "setup_quality", 0.0
                        ),
                        present=group_scores.setup_present,
                    ),
                    AlphaTriggerGroupInput(
                        group="institutional_flow",
                        score=group_scores.flow_score,
                        configured_weight=config.alpha_trigger.group_weights.get(
                            "institutional_flow", 0.0
                        ),
                        present=group_scores.flow_present,
                    ),
                    AlphaTriggerGroupInput(
                        group="market_context",
                        score=SignalAlphaTriggerProjection._score_sector_market_context(
                            request.sector_context_evidence
                        ),
                        configured_weight=config.alpha_trigger.group_weights.get(
                            "market_context", 0.0
                        ),
                        present=SignalAlphaTriggerProjection._sector_context_present(
                            request.sector_context_evidence
                        ),
                    ),
                    AlphaTriggerGroupInput(
                        group="company_quality_context",
                        score=SignalAlphaTriggerProjection._score_company_quality(
                            request.company_quality_context_evidence
                        ),
                        configured_weight=config.alpha_trigger.group_weights.get(
                            "company_quality_context", 0.0
                        ),
                        present=SignalAlphaTriggerProjection._company_quality_present(
                            request.company_quality_context_evidence
                        ),
                    ),
                ),
                setup_phase=request.setup_phase,
                flow_confirmation_evidence=request.flow_confirmation_evidence,
            )
        )

    @staticmethod
    def _score_sector_market_context(
        ev: SectorContextEvidence | None,
    ) -> float:
        if ev is None:
            return 0.0
        return {
            "BULLISH": 75.0,
            "NEUTRAL": 50.0,
            "BEARISH": 25.0,
        }.get(ev.sector_regime, 0.0)

    @staticmethod
    def _sector_context_present(
        ev: SectorContextEvidence | None,
    ) -> bool:
        return ev is not None and ev.coverage_score > 0.0 and ev.sector_regime != "UNKNOWN"

    @staticmethod
    def _score_company_quality(
        ev: CompanyQualityContextEvidence | None,
    ) -> float:
        if ev is None or ev.aggregate_score is None:
            return 0.0
        return ev.aggregate_score

    @staticmethod
    def _company_quality_present(
        ev: CompanyQualityContextEvidence | None,
    ) -> bool:
        return ev is not None and ev.coverage_score > 0.0 and ev.aggregate_score is not None
