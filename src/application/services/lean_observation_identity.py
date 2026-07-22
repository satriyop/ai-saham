"""Lean observation identity — the DQ-003 lean-contract compatibility tag.

Layer: Application (pure, deterministic, no I/O)

The full three-part artifact identity (`artifact_id` + `semantic_compatibility_id`
+ `ArtifactProvenance`, see ``signal_artifact_identity.py``) mandates all three
parts and a per-config-path material registry. DQ-003 deliberately ships a lean
subset: an explicit ``observation_contract`` string plus a
``semantic_compatibility_id`` derived from a *whole-config content hash*. The
heavy apparatus stays parked (built, tested, trigger-gated) — see
``tasks/done/audit_data_quality.md`` → "Lean identity amendment (2026-07-21)".

Why a whole-config hash rather than the enumerated material-path registry: a
whole-config hash cannot silently fail to fork when an unregistered config path
changes. Over-forking on a cosmetic edit is safe; silent under-forking is the
failure mode this contract removes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_semantic_contract import (
    EVIDENCE_CONTRACT_VERSION,
    SEMANTIC_ENGINE_VERSION,
)


@dataclass(frozen=True)
class LeanObservationIdentity:
    """Narrow value object carrying only the two lean-contract identity parts.

    Unlike ``SignalArtifactIdentity`` (which mandates ``artifact_id`` and a full
    ``ArtifactProvenance``), this binds exactly the two fields the lean DQ-003
    capture path persists: the ``observation_contract`` label and the
    whole-config-hash ``semantic_compatibility_id`` cohort tag.
    """

    observation_contract: str
    semantic_compatibility_id: SemanticCompatibilityId

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_contract, str)
            or not self.observation_contract.strip()
            or self.observation_contract != self.observation_contract.strip()
        ):
            raise ValueError(
                "observation_contract must be a non-empty trimmed string, got "
                f"{self.observation_contract!r}"
            )
        if not isinstance(self.semantic_compatibility_id, SemanticCompatibilityId):
            raise ValueError(
                "semantic_compatibility_id must be a SemanticCompatibilityId, got "
                f"{type(self.semantic_compatibility_id).__name__}"
            )


def resolve_lean_semantic_compatibility_id(
    resolved_config_canonical: str,
) -> SemanticCompatibilityId:
    """Hash the whole resolved config content into a compatibility cohort tag.

    ``resolved_config_canonical`` must already be a deterministic canonical
    rendering of the resolved scoring config content (the caller/adapter owns
    reading the files and canonicalizing; this function performs no I/O). The
    schema, semantic-engine, and evidence-contract versions are folded in so a
    contract-version bump also forks the cohort.

    Deterministic: the same config content and versions always produce the same
    id; any change to the config content or a version forks it.
    """
    if not isinstance(resolved_config_canonical, str):
        raise ValueError(
            "resolved_config_canonical must be a str, got "
            f"{type(resolved_config_canonical).__name__}"
        )
    digest = hashlib.sha256(
        (
            resolved_config_canonical
            + str(CANDIDATE_OBSERVATION_SCHEMA_VERSION)
            + SEMANTIC_ENGINE_VERSION
            + EVIDENCE_CONTRACT_VERSION
        ).encode("utf-8")
    ).hexdigest()
    return SemanticCompatibilityId("sha256:" + digest)
