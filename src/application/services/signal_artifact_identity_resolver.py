"""Pure identity resolver — deterministic hash of canonical domain JSON.

Layer: Application (pure, stateless; no I/O, no persistence)
"""

import hashlib

from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactIdentityDimensions,
    ArtifactProvenance,
    SemanticCompatibilityDimensions,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)


class SignalArtifactIdentityResolver:
    """Stateless resolver that computes artifact and semantic compatibility IDs.

    Every method is deterministic given identical domain dimensions.
    No I/O, no persistence, no side effects.
    """

    @staticmethod
    def resolve_semantic_compatibility_id(
        dimensions: SemanticCompatibilityDimensions,
    ) -> SemanticCompatibilityId:
        if not isinstance(dimensions, SemanticCompatibilityDimensions):
            raise TypeError("semantic_dimensions must be SemanticCompatibilityDimensions")
        canonical_json = dimensions.to_canonical_json()
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return SemanticCompatibilityId(f"sha256:{digest}")

    @staticmethod
    def resolve_artifact_id(
        dimensions: ArtifactIdentityDimensions,
    ) -> ArtifactId:
        if not isinstance(dimensions, ArtifactIdentityDimensions):
            raise TypeError("artifact_dimensions must be ArtifactIdentityDimensions")
        canonical_json = dimensions.to_canonical_json()
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return ArtifactId(f"sha256:{digest}")

    def resolve(
        self,
        *,
        semantic_dimensions: SemanticCompatibilityDimensions,
        artifact_dimensions: ArtifactIdentityDimensions,
        provenance: ArtifactProvenance,
    ) -> SignalArtifactIdentity:
        if not isinstance(semantic_dimensions, SemanticCompatibilityDimensions):
            raise TypeError("semantic_dimensions must be SemanticCompatibilityDimensions")
        if not isinstance(artifact_dimensions, ArtifactIdentityDimensions):
            raise TypeError("artifact_dimensions must be ArtifactIdentityDimensions")
        if not isinstance(provenance, ArtifactProvenance):
            raise TypeError("provenance must be ArtifactProvenance")

        semantic_compatibility_id = self.resolve_semantic_compatibility_id(
            semantic_dimensions,
        )

        if artifact_dimensions.semantic_compatibility_id != semantic_compatibility_id:
            raise ValueError(
                "artifact semantic_compatibility_id does not match "
                "resolved semantic compatibility ID"
            )

        if artifact_dimensions.universe_snapshot_id != provenance.universe_snapshot_id:
            raise ValueError("artifact and provenance universe_snapshot_id must match")

        artifact_id = self.resolve_artifact_id(artifact_dimensions)

        return SignalArtifactIdentity(
            artifact_id=artifact_id,
            semantic_compatibility_id=semantic_compatibility_id,
            provenance=provenance,
        )
