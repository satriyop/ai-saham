"""Lean observation identity — the narrow contract/cohort pair a capture writes.

Layer: Application (pure, deterministic, no I/O)

The full three-part artifact identity (`artifact_id` + `semantic_compatibility_id`
+ `ArtifactProvenance`, see ``signal_artifact_identity.py``) mandates all three
parts and a per-config-path material registry. DQ-003 deliberately ships a lean
subset: an explicit ``observation_contract`` string plus a
``semantic_compatibility_id`` cohort tag. The heavy apparatus stays parked
(built, tested, trigger-gated) — see ``tasks/done/audit_data_quality.md`` →
"Lean identity amendment (2026-07-21)".

ADR-068 amendment: this module no longer resolves the cohort tag. The
accumulation ``semantic_compatibility_id`` is now measured behaviour, resolved
by ``behavioral_cohort_identity.resolve_accumulation_cohort_identity``. The
config-byte formula (``lean_accumulation_compatibility.v2``) and the hand-typed
engine/evidence version constants it folded are deleted with no alias, fallback,
or dual path. What remains here is the value object that carries the resulting
pair to ``EnsureAccumulationPolicySnapshotsUseCase``,
``BackfillSignalObservationsUseCase``, and
``RecordAccumulationObservationsUseCase``.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)

# ADR-059 v2 policy-snapshot binding contract. Survives ADR-068 untouched (§8):
# it names which closed snapshot set a cohort is bound to, and is consumed by
# accumulation readiness rather than by identity resolution.
POLICY_SNAPSHOT_BINDING_CONTRACT_V2 = "production_policy_snapshot.v2"


@dataclass(frozen=True)
class LeanObservationIdentity:
    """Narrow value object carrying only the two lean-contract identity parts.

    Unlike ``SignalArtifactIdentity`` (which mandates ``artifact_id`` and a full
    ``ArtifactProvenance``), this binds exactly the two fields the lean DQ-003
    capture path persists: the ``observation_contract`` label and the
    ``semantic_compatibility_id`` cohort tag.
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
