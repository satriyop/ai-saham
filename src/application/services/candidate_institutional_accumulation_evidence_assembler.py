"""Institutional accumulation evidence assembly, shared by evidence coordinators.

Layer: Application
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Callable

from src.application.services.candidate_evidence_data_loader import (
    InstitutionalEvidenceInputs,
)

if TYPE_CHECKING:
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceBuilder,
    )
    from src.domain.value_objects.bandar_detector import BandarDetectorSnapshot
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )


class CandidateInstitutionalAccumulationEvidenceAssembler:
    """Builds InstitutionalAccumulationEvidence from pre-loaded repository inputs."""

    def __init__(
        self,
        builder_factory: Callable[[], "InstitutionalAccumulationEvidenceBuilder"],
    ) -> None:
        self._builder_factory = builder_factory

    def assemble(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        inputs: InstitutionalEvidenceInputs,
        bandar_snapshot: "BandarDetectorSnapshot | None",
    ) -> "InstitutionalAccumulationEvidence | None":
        from src.application.services.institutional_accumulation_evidence_builder import (
            InstitutionalAccumulationEvidenceRequest,
        )

        builder = self._builder_factory()
        return builder.build(
            InstitutionalAccumulationEvidenceRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                broker_daily_flows=inputs.broker_daily_flows,
                foreign_flow_points=inputs.foreign_flow_points,
                broker_summaries=inputs.broker_summaries,
                bandar_snapshot=bandar_snapshot,
                candles=inputs.candles,
            )
        )
