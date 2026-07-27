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
from src.domain.value_objects.alpha_trigger_score import (
    SECTOR_CONTEXT_EVIDENCE_NAME,
    EvidenceAuthorityStatus,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalEvidenceRequest
    from src.application.services.signal_engine_config import SignalEngineConfig
    from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScores
    from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
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
        setup_source_auth = SignalAlphaTriggerProjection._source_authority_fraction(
            request, group="setup"
        )
        flow_source_auth = SignalAlphaTriggerProjection._source_authority_fraction(
            request, group="flow"
        )
        flow_component_coverage = SignalAlphaTriggerProjection._flow_component_coverage(
            request.flow_confirmation_evidence
        )

        return aggregator.aggregate(
            AlphaTriggerAggregationRequest(
                horizon=request.horizon or config.alpha_trigger.default_horizon,
                groups=(
                    AlphaTriggerGroupInput(
                        group="setup_quality",
                        score=group_scores.setup_group_score,
                        configured_weight=config.alpha_trigger.group_weights.get(
                            "setup_quality", 0.0
                        ),
                        present=group_scores.setup_present,
                        coverage_fraction=1.0 if group_scores.setup_present else 0.0,
                        authority_fraction=(
                            setup_source_auth if group_scores.setup_present else 0.0
                        ),
                    ),
                    AlphaTriggerGroupInput(
                        group="institutional_flow",
                        score=group_scores.flow_group_score,
                        configured_weight=config.alpha_trigger.group_weights.get(
                            "institutional_flow", 0.0
                        ),
                        present=group_scores.flow_present,
                        coverage_fraction=(
                            flow_component_coverage if group_scores.flow_present else 0.0
                        ),
                        authority_fraction=(
                            flow_source_auth * flow_component_coverage
                            if group_scores.flow_present
                            else 0.0
                        ),
                    ),
                    AlphaTriggerGroupInput(
                        group=SECTOR_CONTEXT_EVIDENCE_NAME,
                        score=SignalAlphaTriggerProjection._score_sector_context(
                            request.sector_context_evidence
                        ),
                        configured_weight=config.alpha_trigger.group_weights.get(
                            SECTOR_CONTEXT_EVIDENCE_NAME, 0.0
                        ),
                        present=SignalAlphaTriggerProjection._sector_context_present(
                            request.sector_context_evidence
                        ),
                        coverage_fraction=SignalAlphaTriggerProjection._diagnostic_coverage(
                            present=SignalAlphaTriggerProjection._sector_context_present(
                                request.sector_context_evidence
                            ),
                            config=config,
                            group=SECTOR_CONTEXT_EVIDENCE_NAME,
                        ),
                        authority_fraction=0.0,
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
                        coverage_fraction=SignalAlphaTriggerProjection._diagnostic_coverage(
                            present=SignalAlphaTriggerProjection._company_quality_present(
                                request.company_quality_context_evidence
                            ),
                            config=config,
                            group="company_quality_context",
                        ),
                        authority_fraction=0.0,
                    ),
                ),
                setup_phase=request.setup_phase,
                flow_confirmation_evidence=request.flow_confirmation_evidence,
            )
        )

    @staticmethod
    def _source_authority_fraction(
        request: AssessSignalEvidenceRequest,
        *,
        group: str,
    ) -> float:
        canonical = request.canonical_evidence
        if canonical is None:
            return 0.0
        group_input = canonical.setup if group == "setup" else canonical.flow
        if group_input is None:
            return 0.0
        return group_input.availability.settled_authority_fraction

    @staticmethod
    def _flow_component_coverage(
        flow_ev: "FlowConfirmationEvidence | None",
    ) -> float:
        if flow_ev is None:
            return 0.0
        return max(0.0, min(1.0, float(flow_ev.component_coverage)))

    @staticmethod
    def _diagnostic_coverage(
        *,
        present: bool,
        config: SignalEngineConfig,
        group: str,
    ) -> float:
        """Diagnostic groups contribute to configured coverage when present,
        but never to authority coverage."""
        if not present:
            return 0.0
        registration = config.alpha_trigger.evidence_registrations.get(group)
        if registration is not None and registration.status == EvidenceAuthorityStatus.PRODUCTION:
            return 1.0
        return 1.0

    @staticmethod
    def _score_sector_context(
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
