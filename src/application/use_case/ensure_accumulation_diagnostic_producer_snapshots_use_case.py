"""Ensure immutable diagnostic producer snapshots before observation writes.

Layer: Application.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from src.application.services.accumulation_diagnostic_producer_payloads import (
    AccumulationDiagnosticProducerInputs,
    build_all_accumulation_diagnostic_producer_payloads,
)
from src.domain.ports.learning_artifact_repositories import (
    LearningDiagnosticProducerSnapshotRepository,
)
from src.domain.value_objects.diagnostic_producer_identity import (
    ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS,
    AccumulationDiagnosticBinding,
    DiagnosticProducerSnapshot,
    build_accumulation_diagnostic_bindings,
)
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.domain.value_objects.signal_artifact_schema import (
    ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class EnsureAccumulationDiagnosticProducerSnapshotsRequest:
    inputs: AccumulationDiagnosticProducerInputs
    created_at: datetime
    source_revision: str


@dataclass(frozen=True)
class EnsureAccumulationDiagnosticProducerSnapshotsResponse:
    inserted_count: int
    reused_count: int
    snapshots: tuple[DiagnosticProducerSnapshot, ...]
    bindings: Mapping[str, AccumulationDiagnosticBinding]


class EnsureAccumulationDiagnosticProducerSnapshotsUseCase:
    """Persist the exact producer set and return its schema-14 bindings."""

    def __init__(self, repository: LearningDiagnosticProducerSnapshotRepository) -> None:
        self._repository = repository

    def execute(
        self,
        request: EnsureAccumulationDiagnosticProducerSnapshotsRequest,
    ) -> EnsureAccumulationDiagnosticProducerSnapshotsResponse:
        descriptors = build_all_accumulation_diagnostic_producer_payloads(request.inputs)
        if set(descriptors) != set(ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS):
            raise RuntimeError("diagnostic producer descriptor set is incomplete")
        snapshots = tuple(
            DiagnosticProducerSnapshot.create(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                producer_id=producer_id,
                producer_contract_id=descriptors[producer_id].producer_contract_id,
                formula_id=descriptors[producer_id].formula_id,
                canonical_payload=descriptors[producer_id].canonical_payload,
                source_revision=request.source_revision,
                created_at=request.created_at,
            )
            for producer_id in ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS
        )
        inserted, reused = self._repository.add_diagnostic_producer_snapshots_atomic(snapshots)
        bindings = build_accumulation_diagnostic_bindings(
            snapshots,
            observation_schema_version=ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
        )
        return EnsureAccumulationDiagnosticProducerSnapshotsResponse(
            inserted_count=inserted,
            reused_count=reused,
            snapshots=snapshots,
            bindings=bindings,
        )
