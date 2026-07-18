"""Adversarial tests for the pure identity resolver (Slice 2).

Tests use locally defined fixtures built from public domain types.
Expected hash values are hard-coded; never computed by the resolver.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest

from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactIdentityDimensions,
    ArtifactProvenance,
    ArtifactSourceProvenance,
    SemanticCompatibilityDimensions,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)
from src.application.services.signal_artifact_identity_resolver import (
    SignalArtifactIdentityResolver,
)

# ---------------------------------------------------------------------------
# Hard-coded known SHA-256 vectors (never computed from the resolver)
# ---------------------------------------------------------------------------

_KNOWN_SEMANTIC_ID = (
    "sha256:38fa9b84fb8740079828939b4eb1eb08fef2d6dc1774eab0558fd5e945ba1511"
)
_KNOWN_ARTIFACT_ID = (
    "sha256:96ea7e190d7481eb2238889ed318cc3be624d15f8cc447bada1b31d91db6a2c0"
)

_HEX_64_A = "a" * 64
_HEX_64_B = "b" * 64
_HEX_64_C = "c" * 64
_HEX_64_D = "d" * 64
_HEX_64_E = "e" * 64

_ANOTHER_PREFIXED = SemanticCompatibilityId("sha256:" + _HEX_64_D)
_DIFFERENT_PREFIXED = SemanticCompatibilityId("sha256:" + _HEX_64_E)

# ---------------------------------------------------------------------------
# Local fixture builders (independent of domain test module)
# ---------------------------------------------------------------------------


def _known_semantic_dimensions() -> SemanticCompatibilityDimensions:
    """Fixture producing the exact known-vector semantic canonical JSON."""
    return SemanticCompatibilityDimensions(
        observation_contract="accumulation-discovery",
        setup_family="mean_reversion",
        evidence_contract_version="1.0",
        observation_schema_version=3,
        label_schema_version=2,
        semantic_engine_version="3.0.0",
        material_config_hash=_HEX_64_A,
        authority_registrations_hash=_HEX_64_B,
        execution_label_policy_version="1.0",
    )


def _known_artifact_dimensions() -> ArtifactIdentityDimensions:
    """Fixture producing the exact known-vector artifact canonical JSON."""
    return ArtifactIdentityDimensions(
        artifact_type="candidate_observation",
        semantic_compatibility_id=SemanticCompatibilityId(_KNOWN_SEMANTIC_ID),
        effective_session=date(2026, 7, 18),
        ticker="BBCA",
        universe_snapshot_id="univ-001",
        source_snapshot_cutoff_id="cutoff-001",
    )


def _semantic_with(**overrides: Any) -> SemanticCompatibilityDimensions:
    kwargs: dict[str, Any] = dict(
        observation_contract="accumulation-discovery",
        setup_family="mean_reversion",
        evidence_contract_version="1.0",
        observation_schema_version=3,
        label_schema_version=2,
        semantic_engine_version="3.0.0",
        material_config_hash=_HEX_64_A,
        authority_registrations_hash=_HEX_64_B,
        execution_label_policy_version="1.0",
    )
    kwargs.update(overrides)
    return SemanticCompatibilityDimensions(**kwargs)


def _artifact_with(**overrides: Any) -> ArtifactIdentityDimensions:
    kwargs: dict[str, Any] = dict(
        artifact_type="candidate_observation",
        semantic_compatibility_id=SemanticCompatibilityId(_KNOWN_SEMANTIC_ID),
        effective_session=date(2026, 7, 18),
        ticker="BBCA",
        universe_snapshot_id="univ-001",
        source_snapshot_cutoff_id="cutoff-001",
    )
    kwargs.update(overrides)
    return ArtifactIdentityDimensions(**kwargs)


def _source_with(**overrides: Any) -> ArtifactSourceProvenance:
    kwargs: dict[str, Any] = dict(
        source_family="candles",
        provider="yahoo_finance",
        source_snapshot_id="snap-001",
        observed_through=date(2026, 7, 17),
        available_at=datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc),
        cutoff_at=datetime(2026, 7, 18, 6, 0, 0, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return ArtifactSourceProvenance(**kwargs)


def _provenance_with(**overrides: Any) -> ArtifactProvenance:
    kwargs: dict[str, Any] = dict(
        application_revision="abc1234",
        complete_config_hash=_HEX_64_A,
        complete_authority_registry_hash=_HEX_64_B,
        universe_snapshot_id="univ-001",
        idx_calendar_version="2026.1",
        session_rule_version="1.0",
        decision_at=datetime(2026, 7, 18, 7, 0, 0, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 18),
        sources=(_source_with(),),
        invocation_command="saham screen accum",
        invocation_actor="test_user",
    )
    kwargs.update(overrides)
    return ArtifactProvenance(**kwargs)


# ---------------------------------------------------------------------------
# Known vector tests
# ---------------------------------------------------------------------------


class TestKnownVectors:
    """Hard-coded expected IDs from independently computed SHA-256."""

    def test_known_semantic_id(self) -> None:
        dims = _known_semantic_dimensions()
        result = SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(
            dims,
        )
        assert result.value == _KNOWN_SEMANTIC_ID

    def test_known_artifact_id(self) -> None:
        dims = _known_artifact_dimensions()
        result = SignalArtifactIdentityResolver.resolve_artifact_id(dims)
        assert result.value == _KNOWN_ARTIFACT_ID

    def test_sha256_prefix_format(self) -> None:
        sem_id = SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(
            _known_semantic_dimensions(),
        )
        art_id = SignalArtifactIdentityResolver.resolve_artifact_id(
            _known_artifact_dimensions(),
        )
        for sid in (sem_id.value, art_id.value):
            assert sid.startswith("sha256:")
            assert len(sid) == 7 + 64  # "sha256:" + 64 hex chars
            hex_part = sid[7:]
            assert all(c in "0123456789abcdef" for c in hex_part)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Repeated resolution produces identical IDs."""

    def test_repeated_semantic(self) -> None:
        dims = _known_semantic_dimensions()
        a = SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(dims)
        b = SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(dims)
        assert a == b

    def test_repeated_artifact(self) -> None:
        dims = _known_artifact_dimensions()
        a = SignalArtifactIdentityResolver.resolve_artifact_id(dims)
        b = SignalArtifactIdentityResolver.resolve_artifact_id(dims)
        assert a == b

    def test_repeated_combined(self) -> None:
        resolver = SignalArtifactIdentityResolver()
        a = resolver.resolve(
            semantic_dimensions=_known_semantic_dimensions(),
            artifact_dimensions=_known_artifact_dimensions(),
            provenance=_provenance_with(),
        )
        b = resolver.resolve(
            semantic_dimensions=_known_semantic_dimensions(),
            artifact_dimensions=_known_artifact_dimensions(),
            provenance=_provenance_with(),
        )
        assert a == b


# ---------------------------------------------------------------------------
# Semantic sensitivity
# ---------------------------------------------------------------------------


class TestSemanticSensitivity:
    """Changing any semantic dimension changes the semantic ID."""

    _BASELINE = _known_semantic_dimensions()

    def _assert_changes(self, **overrides: Any) -> None:
        modified = _semantic_with(**overrides)
        baseline_id = SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(
            self._BASELINE,
        )
        modified_id = (
            SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(
                modified,
            )
        )
        assert baseline_id != modified_id

    def test_observation_contract(self) -> None:
        self._assert_changes(observation_contract="swing_setup")

    def test_setup_family(self) -> None:
        self._assert_changes(setup_family="trend_following")

    def test_evidence_contract_version(self) -> None:
        self._assert_changes(evidence_contract_version="2.0")

    def test_observation_schema_version(self) -> None:
        self._assert_changes(observation_schema_version=4)

    def test_label_schema_version(self) -> None:
        self._assert_changes(label_schema_version=3)

    def test_semantic_engine_version(self) -> None:
        self._assert_changes(semantic_engine_version="4.0.0")

    def test_material_config_hash(self) -> None:
        self._assert_changes(material_config_hash=_HEX_64_C)

    def test_authority_registrations_hash(self) -> None:
        self._assert_changes(authority_registrations_hash=_HEX_64_C)

    def test_execution_label_policy_version(self) -> None:
        self._assert_changes(execution_label_policy_version="2.0")


# ---------------------------------------------------------------------------
# Artifact sensitivity
# ---------------------------------------------------------------------------


class TestArtifactSensitivity:
    """Changing any artifact dimension changes the artifact ID."""

    _BASELINE = _known_artifact_dimensions()

    def _assert_changes(self, **overrides: Any) -> None:
        modified = _artifact_with(**overrides)
        baseline_id = SignalArtifactIdentityResolver.resolve_artifact_id(
            self._BASELINE,
        )
        modified_id = SignalArtifactIdentityResolver.resolve_artifact_id(modified)
        assert baseline_id != modified_id

    def test_artifact_type(self) -> None:
        self._assert_changes(artifact_type="swing_observation")

    def test_semantic_compatibility_id(self) -> None:
        self._assert_changes(semantic_compatibility_id=_ANOTHER_PREFIXED)

    def test_effective_session(self) -> None:
        self._assert_changes(effective_session=date(2026, 7, 17))

    def test_ticker(self) -> None:
        self._assert_changes(ticker="BBRI")

    def test_universe_snapshot_id(self) -> None:
        self._assert_changes(universe_snapshot_id="univ-002")

    def test_source_snapshot_cutoff_id(self) -> None:
        self._assert_changes(source_snapshot_cutoff_id="cutoff-002")


# ---------------------------------------------------------------------------
# Provenance isolation
# ---------------------------------------------------------------------------


class TestProvenanceIsolation:
    """Changing provenance-only fields must not alter either ID."""

    def _assert_ids_unchanged(self, **prov_overrides: Any) -> None:
        sem_dims = _known_semantic_dimensions()
        art_dims = _known_artifact_dimensions()
        expected_sem_id = SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(
            sem_dims,
        )
        expected_art_id = SignalArtifactIdentityResolver.resolve_artifact_id(
            art_dims,
        )

        resolver = SignalArtifactIdentityResolver()
        result = resolver.resolve(
            semantic_dimensions=sem_dims,
            artifact_dimensions=art_dims,
            provenance=_provenance_with(**prov_overrides),
        )
        assert result.semantic_compatibility_id == expected_sem_id
        assert result.artifact_id == expected_art_id

    def test_application_revision(self) -> None:
        self._assert_ids_unchanged(application_revision="def5678")

    def test_complete_config_hash(self) -> None:
        self._assert_ids_unchanged(complete_config_hash=_HEX_64_C)

    def test_complete_authority_registry_hash(self) -> None:
        self._assert_ids_unchanged(complete_authority_registry_hash=_HEX_64_C)

    def test_decision_at(self) -> None:
        self._assert_ids_unchanged(
            decision_at=datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc),
        )

    def test_captured_at(self) -> None:
        self._assert_ids_unchanged(
            captured_at=datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc),
        )

    def test_source_provenance_facts(self) -> None:
        self._assert_ids_unchanged(
            sources=(
                _source_with(
                    source_family="broker_summaries",
                    provider="idx",
                    source_snapshot_id="snap-002",
                ),
            ),
        )

    def test_invocation_command(self) -> None:
        self._assert_ids_unchanged(invocation_command="saham analyze swing")

    def test_invocation_actor(self) -> None:
        self._assert_ids_unchanged(invocation_actor="different_user")


# ---------------------------------------------------------------------------
# Binding validation
# ---------------------------------------------------------------------------


class TestBindingValidation:
    """Semantic and universe mismatches raise ValueError."""

    def test_mismatched_semantic_compatibility_id(self) -> None:
        art_dims = _artifact_with(
            semantic_compatibility_id=_DIFFERENT_PREFIXED,
        )
        resolver = SignalArtifactIdentityResolver()
        with pytest.raises(
            ValueError,
            match="artifact semantic_compatibility_id does not match",
        ):
            resolver.resolve(
                semantic_dimensions=_known_semantic_dimensions(),
                artifact_dimensions=art_dims,
                provenance=_provenance_with(),
            )

    def test_mismatched_universe_snapshot_id(self) -> None:
        art_dims = _artifact_with(universe_snapshot_id="univ-999")
        prov = _provenance_with(universe_snapshot_id="univ-999-but-provenance")
        resolver = SignalArtifactIdentityResolver()
        with pytest.raises(
            ValueError,
            match="artifact and provenance universe_snapshot_id must match",
        ):
            resolver.resolve(
                semantic_dimensions=_known_semantic_dimensions(),
                artifact_dimensions=art_dims,
                provenance=prov,
            )


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------


class TestTypeValidation:
    """Wrong argument types raise TypeError, not AttributeError."""

    def test_standalone_semantic_wrong_type(self) -> None:
        with pytest.raises(
            TypeError,
            match="semantic_dimensions must be SemanticCompatibilityDimensions",
        ):
            SignalArtifactIdentityResolver.resolve_semantic_compatibility_id(
                "bad",  # type: ignore[arg-type]
            )

    def test_standalone_artifact_wrong_type(self) -> None:
        with pytest.raises(
            TypeError,
            match="artifact_dimensions must be ArtifactIdentityDimensions",
        ):
            SignalArtifactIdentityResolver.resolve_artifact_id(
                "bad",  # type: ignore[arg-type]
            )

    def test_wrong_semantic_type(self) -> None:
        resolver = SignalArtifactIdentityResolver()
        with pytest.raises(
            TypeError,
            match="semantic_dimensions must be SemanticCompatibilityDimensions",
        ):
            resolver.resolve(
                semantic_dimensions="not-dimensions",  # type: ignore[arg-type]
                artifact_dimensions=_known_artifact_dimensions(),
                provenance=_provenance_with(),
            )

    def test_wrong_artifact_type(self) -> None:
        resolver = SignalArtifactIdentityResolver()
        with pytest.raises(
            TypeError,
            match="artifact_dimensions must be ArtifactIdentityDimensions",
        ):
            resolver.resolve(
                semantic_dimensions=_known_semantic_dimensions(),
                artifact_dimensions="not-dimensions",  # type: ignore[arg-type]
                provenance=_provenance_with(),
            )

    def test_wrong_provenance_type(self) -> None:
        resolver = SignalArtifactIdentityResolver()
        with pytest.raises(
            TypeError,
            match="provenance must be ArtifactProvenance",
        ):
            resolver.resolve(
                semantic_dimensions=_known_semantic_dimensions(),
                artifact_dimensions=_known_artifact_dimensions(),
                provenance="not-provenance",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Provenance identity and output correctness
# ---------------------------------------------------------------------------


class TestProvenanceAndOutput:
    """Resolver preserves the exact provenance and produces expected IDs."""

    def test_provenance_instance_retained(self) -> None:
        prov = _provenance_with()
        resolver = SignalArtifactIdentityResolver()
        result = resolver.resolve(
            semantic_dimensions=_known_semantic_dimensions(),
            artifact_dimensions=_known_artifact_dimensions(),
            provenance=prov,
        )
        assert result.provenance is prov

    def test_known_vector_ids_in_output(self) -> None:
        resolver = SignalArtifactIdentityResolver()
        result = resolver.resolve(
            semantic_dimensions=_known_semantic_dimensions(),
            artifact_dimensions=_known_artifact_dimensions(),
            provenance=_provenance_with(),
        )
        assert result.semantic_compatibility_id.value == _KNOWN_SEMANTIC_ID
        assert result.artifact_id.value == _KNOWN_ARTIFACT_ID
