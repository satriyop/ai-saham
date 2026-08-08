"""Immutable diagnostic-producer snapshots and observation bindings.

These identities describe diagnostic-only producer semantics. They never
participate directly in Signal, Risk, TradeSetup, or Action authority.

Layer: Domain (pure value objects; no I/O).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractError,
    canonical_json,
)

DIAGNOSTIC_PRODUCER_SNAPSHOT_CONTRACT = "diagnostic_producer_snapshot.v1"
DIAGNOSTIC_BINDING_CONTRACT = "diagnostic_binding.accum.v1"

DIAGNOSTIC_ID_MCE_SCREEN_DISPLAY = "mce.screen_display"
DIAGNOSTIC_ID_SECTOR_PEER_CONTEXT = "sector.peer_context"
DIAGNOSTIC_ID_INSTITUTIONAL_ACCUMULATION = "institutional.accumulation_bag"
DIAGNOSTIC_ID_COMPANY_QUALITY = "company_quality.bag"

PRODUCER_ID_ALPHA_TRIGGER = "diagnostic.alpha_trigger_projection"
PRODUCER_ID_SECTOR_PEER_CONTEXT = "diagnostic.sector_peer_context"
PRODUCER_ID_INSTITUTIONAL_ACCUMULATION = "diagnostic.institutional_accumulation"
PRODUCER_ID_COMPANY_QUALITY = "diagnostic.company_quality_context"
PRODUCER_ID_TICKER_PROFILE = "diagnostic.ticker_profile"
PRODUCER_ID_MARKET_CONTEXT = "diagnostic.market_context.frozen"

ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS: tuple[str, ...] = (
    PRODUCER_ID_ALPHA_TRIGGER,
    PRODUCER_ID_SECTOR_PEER_CONTEXT,
    PRODUCER_ID_INSTITUTIONAL_ACCUMULATION,
    PRODUCER_ID_COMPANY_QUALITY,
    PRODUCER_ID_TICKER_PROFILE,
    PRODUCER_ID_MARKET_CONTEXT,
)

ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS: Mapping[str, tuple[str, ...]] = {
    DIAGNOSTIC_ID_MCE_SCREEN_DISPLAY: (PRODUCER_ID_MARKET_CONTEXT,),
    DIAGNOSTIC_ID_SECTOR_PEER_CONTEXT: (
        PRODUCER_ID_ALPHA_TRIGGER,
        PRODUCER_ID_SECTOR_PEER_CONTEXT,
    ),
    DIAGNOSTIC_ID_INSTITUTIONAL_ACCUMULATION: (
        PRODUCER_ID_ALPHA_TRIGGER,
        PRODUCER_ID_INSTITUTIONAL_ACCUMULATION,
    ),
    DIAGNOSTIC_ID_COMPANY_QUALITY: (
        PRODUCER_ID_ALPHA_TRIGGER,
        PRODUCER_ID_COMPANY_QUALITY,
        PRODUCER_ID_TICKER_PROFILE,
    ),
}


def _sha256_id(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _require_exact_non_empty(field: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise LearningContractError(
            f"{field} must be an exact non-empty str without surrounding whitespace"
        )
    return value


@dataclass(frozen=True)
class DiagnosticProducerSnapshot:
    """One immutable, purpose-scoped diagnostic producer contract snapshot."""

    snapshot_id: str
    schema_version: int
    contract_id: str
    purpose: AssessmentPurpose
    producer_id: str
    producer_contract_id: str
    formula_id: str
    canonical_payload: Mapping[str, Any]
    payload_digest: str
    source_revision: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        purpose: AssessmentPurpose,
        producer_id: str,
        producer_contract_id: str,
        formula_id: str,
        canonical_payload: Mapping[str, Any],
        source_revision: str,
        created_at: datetime,
    ) -> "DiagnosticProducerSnapshot":
        if purpose is not AssessmentPurpose.ACCUMULATION_DISCOVERY:
            raise LearningContractError(
                "diagnostic producer snapshots currently support ACCUMULATION_DISCOVERY only"
            )
        producer_id = _require_exact_non_empty("producer_id", producer_id)
        producer_contract_id = _require_exact_non_empty(
            "producer_contract_id", producer_contract_id
        )
        formula_id = _require_exact_non_empty("formula_id", formula_id)
        source_revision = _require_exact_non_empty("source_revision", source_revision)
        if not isinstance(canonical_payload, Mapping) or not canonical_payload:
            raise LearningContractError("canonical_payload must be a non-empty mapping")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise LearningContractError("created_at must be timezone-aware")

        payload = dict(canonical_payload)
        payload_digest = _sha256_id(payload)
        snapshot_id = _sha256_id(
            {
                "contract_id": DIAGNOSTIC_PRODUCER_SNAPSHOT_CONTRACT,
                "purpose": purpose.value,
                "producer_id": producer_id,
                "producer_contract_id": producer_contract_id,
                "payload_digest": payload_digest,
            }
        )
        return cls(
            snapshot_id=snapshot_id,
            schema_version=1,
            contract_id=DIAGNOSTIC_PRODUCER_SNAPSHOT_CONTRACT,
            purpose=purpose,
            producer_id=producer_id,
            producer_contract_id=producer_contract_id,
            formula_id=formula_id,
            canonical_payload=payload,
            payload_digest=payload_digest,
            source_revision=source_revision,
            created_at=created_at,
        )


@dataclass(frozen=True)
class AccumulationDiagnosticBinding:
    """Closed producer binding for one production-facing diagnostic panel."""

    contract_id: str
    diagnostic_id: str
    compatibility_id: str
    producers: Mapping[str, Mapping[str, str]]

    @classmethod
    def create(
        cls,
        *,
        diagnostic_id: str,
        observation_schema_version: int,
        snapshots: Sequence[DiagnosticProducerSnapshot],
    ) -> "AccumulationDiagnosticBinding":
        required = ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS.get(diagnostic_id)
        if required is None:
            raise LearningContractError(f"unknown diagnostic_id: {diagnostic_id!r}")
        if observation_schema_version != 14:
            raise LearningContractError(
                "diagnostic bindings require accumulation observation schema 14"
            )
        by_id: dict[str, DiagnosticProducerSnapshot] = {}
        for snapshot in snapshots:
            if snapshot.producer_id in by_id:
                raise LearningContractError(
                    f"duplicate producer snapshot: {snapshot.producer_id!r}"
                )
            by_id[snapshot.producer_id] = snapshot
        if set(by_id) != set(required):
            raise LearningContractError(
                f"diagnostic {diagnostic_id!r} producer set mismatch: "
                f"required={sorted(required)!r} actual={sorted(by_id)!r}"
            )
        producers = {
            producer_id: {
                "snapshot_id": by_id[producer_id].snapshot_id,
                "payload_digest": by_id[producer_id].payload_digest,
            }
            for producer_id in sorted(required)
        }
        compatibility_id = _sha256_id(
            {
                "contract_id": DIAGNOSTIC_BINDING_CONTRACT,
                "diagnostic_id": diagnostic_id,
                "observation_schema_version": observation_schema_version,
                "producers": [
                    {
                        "producer_id": producer_id,
                        "snapshot_id": producers[producer_id]["snapshot_id"],
                        "payload_digest": producers[producer_id]["payload_digest"],
                    }
                    for producer_id in sorted(producers)
                ],
            }
        )
        return cls(
            contract_id=DIAGNOSTIC_BINDING_CONTRACT,
            diagnostic_id=diagnostic_id,
            compatibility_id=compatibility_id,
            producers=producers,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "diagnostic_id": self.diagnostic_id,
            "compatibility_id": self.compatibility_id,
            "producers": {key: dict(value) for key, value in self.producers.items()},
        }


def build_accumulation_diagnostic_bindings(
    snapshots: Sequence[DiagnosticProducerSnapshot],
    *,
    observation_schema_version: int,
) -> dict[str, AccumulationDiagnosticBinding]:
    """Build every closed purpose binding from one verified producer set."""

    by_id = {snapshot.producer_id: snapshot for snapshot in snapshots}
    if len(by_id) != len(snapshots) or set(by_id) != set(ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS):
        raise LearningContractError("producer snapshots must be the exact closed accumulation set")
    return {
        diagnostic_id: AccumulationDiagnosticBinding.create(
            diagnostic_id=diagnostic_id,
            observation_schema_version=observation_schema_version,
            snapshots=[by_id[producer_id] for producer_id in required],
        )
        for diagnostic_id, required in ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS.items()
    }
