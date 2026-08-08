"""Small valid diagnostic-producer identities for non-identity-focused tests."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.value_objects.diagnostic_producer_identity import (
    ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS,
    DiagnosticProducerSnapshot,
    build_accumulation_diagnostic_bindings,
)
from src.domain.value_objects.learning_artifacts import AssessmentPurpose


def valid_accumulation_diagnostic_bindings():
    snapshots = tuple(
        DiagnosticProducerSnapshot.create(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            producer_id=producer_id,
            producer_contract_id=f"{producer_id}.v1",
            formula_id=f"{producer_id}.formula.v1",
            canonical_payload={"formula_id": f"{producer_id}.formula.v1", "fixture": True},
            source_revision="ai-saham@test",
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        for producer_id in ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS
    )
    return build_accumulation_diagnostic_bindings(
        snapshots,
        observation_schema_version=15,
    )
