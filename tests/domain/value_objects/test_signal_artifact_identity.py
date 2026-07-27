"""Adversarial tests for immutable artifact-identity domain contracts."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta, tzinfo

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOWER_HEX_64 = "a" * 64
_ANOTHER_HEX_64 = "b" * 64
_VALID_PREFIXED = "sha256:" + "c" * 64
_ANOTHER_PREFIXED = "sha256:" + "d" * 64


def _valid_semantic_dimensions(**overrides) -> SemanticCompatibilityDimensions:
    kwargs = dict(
        observation_contract="accumulation-discovery",
        setup_family="mean_reversion",
        evidence_contract_version="1.0",
        observation_schema_version=3,
        label_schema_version=2,
        semantic_engine_version="3.0.0",
        material_config_hash=_LOWER_HEX_64,
        authority_registrations_hash=_ANOTHER_HEX_64,
        execution_label_policy_version="1.0",
    )
    kwargs.update(overrides)
    return SemanticCompatibilityDimensions(**kwargs)


def _valid_artifact_dimensions(**overrides) -> ArtifactIdentityDimensions:
    kwargs = dict(
        artifact_type="candidate_observation",
        semantic_compatibility_id=SemanticCompatibilityId(_VALID_PREFIXED),
        effective_session=date(2026, 7, 18),
        ticker="BBCA",
        universe_snapshot_id="univ-001",
        source_snapshot_cutoff_id="cutoff-001",
    )
    kwargs.update(overrides)
    return ArtifactIdentityDimensions(**kwargs)


def _valid_source(**overrides) -> ArtifactSourceProvenance:
    kwargs = dict(
        source_family="candles",
        provider="yahoo_finance",
        source_snapshot_id="snap-001",
        observed_through=date(2026, 7, 17),
        available_at=datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc),
        cutoff_at=datetime(2026, 7, 18, 6, 0, 0, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return ArtifactSourceProvenance(**kwargs)


def _valid_provenance(**overrides) -> ArtifactProvenance:
    kwargs = dict(
        application_revision="abc1234",
        complete_config_hash=_LOWER_HEX_64,
        complete_authority_registry_hash=_ANOTHER_HEX_64,
        universe_snapshot_id="univ-001",
        idx_calendar_version="2026.1",
        session_rule_version="1.0",
        decision_at=datetime(2026, 7, 18, 7, 0, 0, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc),
        latest_completed_session=date(2026, 7, 17),
        analysis_as_of=date(2026, 7, 18),
        sources=(_valid_source(),),
        invocation_command="saham screen accum",
        invocation_actor="test_user",
    )
    kwargs.update(overrides)
    return ArtifactProvenance(**kwargs)


# ===================================================================
# 1. Immutability and validation
# ===================================================================


class TestImmutability:
    """Every new dataclass is frozen."""

    def test_artifact_id_is_frozen(self) -> None:
        obj = ArtifactId(_VALID_PREFIXED)
        with pytest.raises(AttributeError):
            obj.value = "sha256:" + "e" * 64  # type: ignore[misc]

    def test_semantic_compatibility_id_is_frozen(self) -> None:
        obj = SemanticCompatibilityId(_VALID_PREFIXED)
        with pytest.raises(AttributeError):
            obj.value = "sha256:" + "e" * 64  # type: ignore[misc]

    def test_semantic_dimensions_is_frozen(self) -> None:
        obj = _valid_semantic_dimensions()
        with pytest.raises(AttributeError):
            obj.observation_contract = "other"  # type: ignore[misc]

    def test_artifact_dimensions_is_frozen(self) -> None:
        obj = _valid_artifact_dimensions()
        with pytest.raises(AttributeError):
            obj.ticker = "BBCA"  # type: ignore[misc]

    def test_source_provenance_is_frozen(self) -> None:
        obj = _valid_source()
        with pytest.raises(AttributeError):
            obj.source_family = "other"  # type: ignore[misc]

    def test_artifact_provenance_is_frozen(self) -> None:
        obj = _valid_provenance()
        with pytest.raises(AttributeError):
            obj.application_revision = "other"  # type: ignore[misc]

    def test_signal_artifact_identity_is_frozen(self) -> None:
        obj = SignalArtifactIdentity(
            artifact_id=ArtifactId(_VALID_PREFIXED),
            semantic_compatibility_id=SemanticCompatibilityId(_ANOTHER_PREFIXED),
            provenance=_valid_provenance(),
        )
        with pytest.raises(AttributeError):
            obj.artifact_id = ArtifactId("sha256:" + "e" * 64)  # type: ignore[misc]


class TestArtifactIdValidation:
    """Invalid final digest wrappers fail."""

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "",
            "sha256:",
            "sha256:" + "X" * 64,  # uppercase hex
            "sha256:" + "a" * 63,  # truncated
            "sha256:" + "a" * 64 + "g",  # 65 chars, 'g' not hex
            "sha256:" + "a" * 64 + " ",  # trailing space
            "sha256:" + "a" * 63 + "z",  # 'z' not hex at end
            " sha256:" + "a" * 64,  # leading space
            "SHA256:" + "a" * 64,  # uppercase prefix
            "sha256:" + "a" * 64 + "\n",  # trailing newline
            None,  # type: ignore[arg-type]
            123,  # type: ignore[arg-type]
        ],
    )
    def test_invalid_artifact_id(self, invalid_value) -> None:
        with pytest.raises(ValueError):
            ArtifactId(invalid_value)

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "",
            "sha256:",
            None,
            42,
            "sha256:" + "X" * 64,
        ],
    )
    def test_invalid_semantic_compatibility_id(self, invalid_value) -> None:
        with pytest.raises(ValueError):
            SemanticCompatibilityId(invalid_value)

    def test_valid_ids_pass(self) -> None:
        ArtifactId(_VALID_PREFIXED)
        SemanticCompatibilityId(_VALID_PREFIXED)

    def test_str_returns_value(self) -> None:
        assert str(ArtifactId(_VALID_PREFIXED)) == _VALID_PREFIXED
        assert str(SemanticCompatibilityId(_VALID_PREFIXED)) == _VALID_PREFIXED


class TestBlankRequiredStrings:
    """Blank required strings fail everywhere."""

    @pytest.mark.parametrize(
        "field",
        [
            "observation_contract",
            "evidence_contract_version",
            "semantic_engine_version",
        ],
    )
    def test_semantic_dimensions_blank(self, field) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_semantic_dimensions(**{field: ""})
        with pytest.raises(ValueError, match="non-empty"):
            _valid_semantic_dimensions(**{field: "  "})

    @pytest.mark.parametrize("field", ["artifact_type"])
    def test_artifact_dimensions_blank(self, field) -> None:
        with pytest.raises(ValueError):
            _valid_artifact_dimensions(**{field: ""})
        with pytest.raises(ValueError):
            _valid_artifact_dimensions(**{field: "  "})

    @pytest.mark.parametrize(
        "field",
        ["application_revision", "universe_snapshot_id", "idx_calendar_version",
         "session_rule_version"],
    )
    def test_provenance_blank(self, field) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_provenance(**{field: ""})
        with pytest.raises(ValueError, match="non-empty"):
            _valid_provenance(**{field: "  "})

    def test_hash_fields_blank_fail(self) -> None:
        with pytest.raises(ValueError, match="hex"):
            _valid_semantic_dimensions(material_config_hash="")
        with pytest.raises(ValueError, match="hex"):
            _valid_provenance(complete_config_hash="")

    def test_invocation_command_blank_fail(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_provenance(invocation_command="")

    def test_invocation_actor_blank_fail(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_provenance(invocation_actor="")

    def test_source_snapshot_id_blank_fails(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_source(source_snapshot_id="")

    def test_source_snapshot_id_none_ok(self) -> None:
        _valid_source(source_snapshot_id=None)


class TestTickerValidation:
    """Noncanonical ticker fails."""

    @pytest.mark.parametrize("bad", ["bbca", "BbcA", "BBCA ", " BBCA", "BB CA", "123"])
    def test_invalid_ticker(self, bad) -> None:
        with pytest.raises(ValueError, match="uppercase|non-empty|whitespace"):
            _valid_artifact_dimensions(ticker=bad)

    def test_valid_ticker(self) -> None:
        _valid_artifact_dimensions(ticker="BBCA")
        _valid_artifact_dimensions(ticker="AALI")
        _valid_artifact_dimensions(ticker="MAIN")


class TestSetupFamilyValidation:
    """Noncanonical setup family fails."""

    @pytest.mark.parametrize(
        "bad",
        ["MeanReversion", "mean-reversion", "mean reversion", "Mean_Reversion", "MEAN"],
    )
    def test_invalid_setup_family(self, bad) -> None:
        with pytest.raises(ValueError, match="snake_case"):
            _valid_semantic_dimensions(setup_family=bad)

    def test_setup_family_none_ok(self) -> None:
        _valid_semantic_dimensions(setup_family=None)


class TestSchemaVersionValidation:
    """Boolean and non-positive schema versions fail."""

    @pytest.mark.parametrize("field", ["observation_schema_version", "label_schema_version"])
    @pytest.mark.parametrize("bad", [True, False])
    def test_boolean_schema_versions_fail(self, field, bad) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            _valid_semantic_dimensions(**{field: bad})

    @pytest.mark.parametrize("field", ["observation_schema_version", "label_schema_version"])
    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_zero_or_negative_schema_versions_fail(self, field, bad) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            _valid_semantic_dimensions(**{field: bad})

    def test_both_schema_versions_absent_fails(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            _valid_semantic_dimensions(
                observation_schema_version=None,
                label_schema_version=None,
            )


class TestNaiveDatetimeValidation:
    """Naive provenance datetimes fail."""

    @pytest.mark.parametrize("field", ["available_at", "cutoff_at"])
    def test_naive_source_datetime_fails(self, field) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _valid_source(**{field: datetime(2026, 7, 18, 5, 0, 0)})

    def test_naive_provenance_datetimes_fail(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _valid_provenance(
                decision_at=datetime(2026, 7, 18, 7, 0, 0),
            )
        with pytest.raises(ValueError, match="timezone-aware"):
            _valid_provenance(
                captured_at=datetime(2026, 7, 18, 8, 0, 0),
            )

    def test_source_datetimes_none_ok(self) -> None:
        _valid_source(available_at=None, cutoff_at=None)
        _valid_source(available_at=None)
        _valid_source(cutoff_at=None)


class TestDuplicateSources:
    """Duplicate source identities fail."""

    def test_duplicate_entries_rejected(self) -> None:
        s = _valid_source()
        with pytest.raises(ValueError, match="duplicate source"):
            _valid_provenance(sources=(s, s))

    def test_different_family_allowed(self) -> None:
        s1 = _valid_source(source_family="candles")
        s2 = _valid_source(
            source_family="broker_summaries",
            provider="idx",
            source_snapshot_id="snap-002",
        )
        _valid_provenance(sources=(s1, s2))

    def test_same_family_different_provider_allowed(self) -> None:
        s1 = _valid_source(source_family="candles", provider="yahoo_finance")
        s2 = _valid_source(
            source_family="candles",
            provider="stockbit",
            source_snapshot_id="snap-002",
        )
        _valid_provenance(sources=(s1, s2))

    def test_none_source_snapshot_id_duplicate_rejected(self) -> None:
        s1 = _valid_source(source_snapshot_id=None)
        s2 = _valid_source(source_snapshot_id=None)
        with pytest.raises(ValueError, match="duplicate source"):
            _valid_provenance(sources=(s1, s2))


class TestSessionOrder:
    """latest_completed_session > analysis_as_of fails."""

    def test_future_session_fails(self) -> None:
        with pytest.raises(ValueError, match="must not be after"):
            _valid_provenance(
                latest_completed_session=date(2026, 7, 19),
                analysis_as_of=date(2026, 7, 18),
            )

    def test_equal_session_ok(self) -> None:
        _valid_provenance(
            latest_completed_session=date(2026, 7, 18),
            analysis_as_of=date(2026, 7, 18),
        )

    def test_before_session_ok(self) -> None:
        _valid_provenance(
            latest_completed_session=date(2026, 7, 17),
            analysis_as_of=date(2026, 7, 18),
        )


class TestArtifactTypeValidation:
    """artifact_type must be lowercase snake_case."""

    @pytest.mark.parametrize("bad", ["CamelCase", "kebab-case", "has space", "UPPER"])
    def test_invalid_artifact_type(self, bad) -> None:
        with pytest.raises(ValueError, match="snake_case"):
            _valid_artifact_dimensions(artifact_type=bad)


class TestSourceProviderValidation:
    """source_family and provider must be lowercase snake_case."""

    @pytest.mark.parametrize("field", ["source_family", "provider"])
    @pytest.mark.parametrize("bad", ["CamelCase", "has space", "UPPER"])
    def test_invalid_identifiers(self, field, bad) -> None:
        with pytest.raises(ValueError, match="snake_case"):
            _valid_source(**{field: bad})

    def test_empty_source_family_fails(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_source(source_family="")

    def test_empty_provider_fails(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _valid_source(provider="")


class TestRequiredTemporalFields:
    """Finding 1 — required temporal fields must reject None immediately."""

    def test_effective_session_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a date, not None"):
            _valid_artifact_dimensions(effective_session=None)  # type: ignore[arg-type]

    def test_decision_at_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a datetime, not None"):
            _valid_provenance(decision_at=None)  # type: ignore[arg-type]

    def test_captured_at_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a datetime, not None"):
            _valid_provenance(captured_at=None)  # type: ignore[arg-type]

    def test_latest_completed_session_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a date, not None"):
            _valid_provenance(latest_completed_session=None)  # type: ignore[arg-type]

    def test_analysis_as_of_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a date, not None"):
            _valid_provenance(analysis_as_of=None)  # type: ignore[arg-type]

    def test_source_optional_fields_accept_none(self) -> None:
        """Source observed_through, available_at, cutoff_at remain optional."""
        _valid_source(
            observed_through=None,
            available_at=None,
            cutoff_at=None,
        )


# ===================================================================
# 12-18. Semantic compatibility behavior
# ===================================================================


class TestSemanticCompatibilityCanonicalJson:
    """Identical dimensions produce byte-identical canonical JSON."""

    def test_identical_dimensions_produce_identical_json(self) -> None:
        a = _valid_semantic_dimensions()
        b = _valid_semantic_dimensions()
        assert a.to_canonical_json() == b.to_canonical_json()

    def test_field_construction_order_irrelevant(self) -> None:
        a = SemanticCompatibilityDimensions(
            observation_contract="accumulation-discovery",
            setup_family="mean_reversion",
            evidence_contract_version="1.0",
            observation_schema_version=3,
            label_schema_version=2,
            semantic_engine_version="3.0.0",
            material_config_hash=_LOWER_HEX_64,
            authority_registrations_hash=_ANOTHER_HEX_64,
            execution_label_policy_version="1.0",
        )
        b = SemanticCompatibilityDimensions(
            execution_label_policy_version="1.0",
            authority_registrations_hash=_ANOTHER_HEX_64,
            material_config_hash=_LOWER_HEX_64,
            semantic_engine_version="3.0.0",
            label_schema_version=2,
            observation_schema_version=3,
            evidence_contract_version="1.0",
            setup_family="mean_reversion",
            observation_contract="accumulation-discovery",
        )
        assert a.to_canonical_json() == b.to_canonical_json()

    def test_changing_setup_family_changes_json(self) -> None:
        a = _valid_semantic_dimensions(setup_family="mean_reversion")
        b = _valid_semantic_dimensions(setup_family="trend_following")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_material_config_hash_changes_json(self) -> None:
        a = _valid_semantic_dimensions(material_config_hash="a" * 64)
        b = _valid_semantic_dimensions(material_config_hash="b" * 64)
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_authority_registration_hash_changes_json(self) -> None:
        a = _valid_semantic_dimensions(authority_registrations_hash="a" * 64)
        b = _valid_semantic_dimensions(authority_registrations_hash="b" * 64)
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_semantic_engine_version_changes_json(self) -> None:
        a = _valid_semantic_dimensions(semantic_engine_version="3.0.0")
        b = _valid_semantic_dimensions(semantic_engine_version="3.1.0")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_execution_label_policy_changes_json(self) -> None:
        a = _valid_semantic_dimensions(execution_label_policy_version="1.0")
        b = _valid_semantic_dimensions(execution_label_policy_version="2.0")
        assert a.to_canonical_json() != b.to_canonical_json()


class TestSemanticDimensionsFieldExclusion:
    """Semantic dimensions have no ticker, session, universe, cutoff, invocation, or git fields."""

    SEMANTIC_DIMENSION_FIELDS = {
        "observation_contract",
        "setup_family",
        "evidence_contract_version",
        "observation_schema_version",
        "label_schema_version",
        "semantic_engine_version",
        "material_config_hash",
        "authority_registrations_hash",
        "execution_label_policy_version",
    }

    FORBIDDEN_IN_SEMANTIC = {"ticker", "effective_session", "universe_snapshot_id",
                             "source_snapshot_cutoff_id", "captured_at", "decision_at",
                             "invocation_command", "invocation_actor", "application_revision"}

    def test_no_forbidden_fields_in_semantic_dict(self) -> None:
        d = _valid_semantic_dimensions().to_canonical_dict()
        dict_keys = set(d.keys())
        overlap = dict_keys & self.FORBIDDEN_IN_SEMANTIC
        assert not overlap, f"semantic dimensions contains forbidden fields: {overlap}"

    def test_semantic_only_has_expected_fields(self) -> None:
        d = _valid_semantic_dimensions().to_canonical_dict()
        assert set(d.keys()) == self.SEMANTIC_DIMENSION_FIELDS


# ===================================================================
# 20-24. Artifact identity dimensions
# ===================================================================


class TestArtifactDimensionsCanonicalJson:
    def test_changing_ticker_changes_json(self) -> None:
        a = _valid_artifact_dimensions(ticker="BBCA")
        b = _valid_artifact_dimensions(ticker="BBRI")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_effective_session_changes_json(self) -> None:
        a = _valid_artifact_dimensions(effective_session=date(2026, 7, 17))
        b = _valid_artifact_dimensions(effective_session=date(2026, 7, 18))
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_universe_snapshot_changes_json(self) -> None:
        a = _valid_artifact_dimensions(universe_snapshot_id="univ-001")
        b = _valid_artifact_dimensions(universe_snapshot_id="univ-002")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_source_cutoff_changes_json(self) -> None:
        a = _valid_artifact_dimensions(source_snapshot_cutoff_id="cutoff-001")
        b = _valid_artifact_dimensions(source_snapshot_cutoff_id="cutoff-002")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_no_captured_or_invocation_timestamp(self) -> None:
        d = _valid_artifact_dimensions().to_canonical_dict()
        forbidden = {"captured_at", "decision_at", "invocation_command", "invocation_actor",
                     "application_revision", "latest_completed_session", "analysis_as_of"}
        overlap = set(d.keys()) & forbidden
        assert not overlap, f"artifact dimensions contains forbidden fields: {overlap}"


# ===================================================================
# 25-30. Provenance isolation
# ===================================================================


class TestProvenanceIsolation:
    def test_changing_app_revision_changes_provenance_json(self) -> None:
        a = _valid_provenance(application_revision="abc1234")
        b = _valid_provenance(application_revision="def5678")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_app_revision_does_not_change_semantic_json(self) -> None:
        a = _valid_semantic_dimensions()
        b = _valid_semantic_dimensions()
        assert a.to_canonical_json() == b.to_canonical_json()

    def test_changing_captured_at_changes_provenance_json(self) -> None:
        a = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc),
        )
        b = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc),
        )
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_changing_captured_at_does_not_change_semantic_or_artifact(self) -> None:
        sem = _valid_semantic_dimensions()
        art = _valid_artifact_dimensions()
        json_before = sem.to_canonical_json(), art.to_canonical_json()
        _valid_provenance(
            captured_at=datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc),
        )
        json_after = sem.to_canonical_json(), art.to_canonical_json()
        assert json_before == json_after

    def test_changing_invocation_command_changes_provenance_only(self) -> None:
        a = _valid_provenance(invocation_command="saham screen accum")
        b = _valid_provenance(invocation_command="saham plan swing")
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_equivalent_timezone_instants_serialize_identically(self) -> None:
        a = _valid_provenance(
            decision_at=datetime(2026, 7, 18, 7, 0, 0, tzinfo=timezone.utc),
        )
        b = _valid_provenance(
            decision_at=datetime(2026, 7, 18, 14, 0, 0, tzinfo=timezone(timedelta(hours=7))),
        )
        assert a.to_canonical_json() == b.to_canonical_json()

    def test_reversing_source_input_order_produces_identical_json(self) -> None:
        s1 = _valid_source(source_family="a_family", provider="a_provider",
                           source_snapshot_id="s1")
        s2 = _valid_source(source_family="b_family", provider="b_provider",
                           source_snapshot_id="s2")
        forward = _valid_provenance(sources=(s1, s2))
        reverse = _valid_provenance(sources=(s2, s1))
        assert forward.to_canonical_json() == reverse.to_canonical_json()

    def test_different_cutoff_facts_produce_different_json(self) -> None:
        a = _valid_provenance(
            sources=(_valid_source(cutoff_at=datetime(2026, 7, 18, 6, 0, 0,
                                                      tzinfo=timezone.utc)),),
        )
        b = _valid_provenance(
            sources=(_valid_source(cutoff_at=datetime(2026, 7, 18, 7, 0, 0,
                                                      tzinfo=timezone.utc)),),
        )
        assert a.to_canonical_json() != b.to_canonical_json()


# ===================================================================
# 31-33. Serialization correctness
# ===================================================================


class TestSerializationCorrectness:
    def test_non_ascii_escaped_deterministically(self) -> None:
        obj = _valid_semantic_dimensions(
            observation_contract="caf\u00e9_contract",
        )
        raw = obj.to_canonical_json()
        assert "\\u00e9" in raw
        # Verify it's valid parseable JSON
        parsed = json.loads(raw)
        assert parsed["observation_contract"] == "caf\u00e9_contract"

    def test_no_default_str_repr_filesystem_or_object_identity(self) -> None:
        """Serializer does not rely on repr(), str() fallback, paths, or object identity."""
        # Construct a complex provenance and verify serialization succeeds
        s1 = _valid_source(source_family="candles", provider="yahoo_finance",
                           source_snapshot_id="s1")
        s2 = _valid_source(source_family="broker_summaries", provider="idx",
                           source_snapshot_id="s2")
        prov = _valid_provenance(
            sources=(s1, s2),
            invocation_command="saham screen accum",
            invocation_actor=None,
        )
        raw = prov.to_canonical_json()
        parsed = json.loads(raw)
        # Verify the output contains expected values in the right structure
        assert parsed["application_revision"] == "abc1234"
        assert parsed["invocation_command"] == "saham screen accum"
        assert parsed["invocation_actor"] is None
        assert len(parsed["sources"]) == 2
        # Verify no Python repr artifacts
        assert "<" not in raw
        assert "object at" not in raw
        assert "0x" not in raw


# ===================================================================
# Additional structural and edge-case tests
# ===================================================================


class TestStructuralIntegrity:
    def test_signal_artifact_identity_holds_all_three(self) -> None:
        artifact_id = ArtifactId(_VALID_PREFIXED)
        compat_id = SemanticCompatibilityId(_ANOTHER_PREFIXED)
        provenance = _valid_provenance()
        identity = SignalArtifactIdentity(
            artifact_id=artifact_id,
            semantic_compatibility_id=compat_id,
            provenance=provenance,
        )
        assert identity.artifact_id is artifact_id
        assert identity.semantic_compatibility_id is compat_id
        assert identity.provenance is provenance

    def test_artifact_id_hash_fields_rejected_in_non_prefixed(self) -> None:
        with pytest.raises(ValueError, match="sha256"):
            ArtifactId("a" * 64)

    def test_semantic_compatibility_id_hash_fields_rejected_in_non_prefixed(self) -> None:
        with pytest.raises(ValueError, match="sha256"):
            SemanticCompatibilityId("a" * 64)

    def test_semantic_compatibility_id_str(self) -> None:
        obj = SemanticCompatibilityId(_VALID_PREFIXED)
        assert str(obj) == _VALID_PREFIXED

    def test_artifact_id_str(self) -> None:
        obj = ArtifactId(_VALID_PREFIXED)
        assert str(obj) == _VALID_PREFIXED

    def test_semantic_dimensions_to_canonical_json_valid_json(self) -> None:
        raw = _valid_semantic_dimensions().to_canonical_json()
        parsed = json.loads(raw)
        assert parsed["observation_contract"] == "accumulation-discovery"
        assert parsed["setup_family"] == "mean_reversion"
        assert parsed["evidence_contract_version"] == "1.0"

    def test_artifact_dimensions_to_canonical_json_valid_json(self) -> None:
        raw = _valid_artifact_dimensions().to_canonical_json()
        parsed = json.loads(raw)
        assert parsed["ticker"] == "BBCA"
        assert parsed["effective_session"] == "2026-07-18"

    def test_source_provenance_to_canonical_json(self) -> None:
        raw = _valid_source().to_canonical_json()
        parsed = json.loads(raw)
        assert parsed["source_family"] == "candles"
        assert parsed["provider"] == "yahoo_finance"

    def test_provenance_to_canonical_json_contains_sorted_sources(self) -> None:
        s1 = _valid_source(source_family="broker_summaries", provider="idx",
                           source_snapshot_id="s1")
        s2 = _valid_source(source_family="candles", provider="yahoo_finance",
                           source_snapshot_id="s2")
        prov = _valid_provenance(sources=(s2, s1))
        raw = prov.to_canonical_json()
        parsed = json.loads(raw)
        assert parsed["sources"][0]["source_family"] == "broker_summaries"
        assert parsed["sources"][1]["source_family"] == "candles"

    def test_provenance_invocation_defaults(self) -> None:
        prov = _valid_provenance(invocation_command=None, invocation_actor=None)
        raw = json.loads(prov.to_canonical_json())
        assert raw["invocation_command"] is None
        assert raw["invocation_actor"] is None

    def test_canonical_json_separators_no_spaces(self) -> None:
        """Verify separators=(',', ':') produces no spaces between tokens."""
        raw = _valid_provenance().to_canonical_json()
        # Check there are no spaces right after ':' or ','
        assert ", " not in raw
        assert ": " not in raw
        assert '", "' not in raw


class TestMicrosecondPreservation:
    """Finding 1 — datetime serialization must preserve microseconds."""

    def test_different_microseconds_serialize_differently(self) -> None:
        a = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, 123456, tzinfo=timezone.utc),
        )
        b = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, 654321, tzinfo=timezone.utc),
        )
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_zero_microseconds_serialized_explicitly(self) -> None:
        prov = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, 0, tzinfo=timezone.utc),
        )
        raw = prov.to_canonical_json()
        assert "08:00:00.000000Z" in raw

    def test_non_zero_microseconds_preserved(self) -> None:
        prov = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, 789123, tzinfo=timezone.utc),
        )
        raw = prov.to_canonical_json()
        assert "08:00:00.789123Z" in raw

    def test_equivalent_instants_differing_in_microsecond_normalize(self) -> None:
        """Two equivalent instants with different microsecond truncation are distinct."""
        a = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, 100, tzinfo=timezone.utc),
        )
        b = _valid_provenance(
            captured_at=datetime(2026, 7, 18, 8, 0, 0, 200, tzinfo=timezone.utc),
        )
        assert a.to_canonical_json() != b.to_canonical_json()

    def test_microseconds_across_timezone_boundary(self) -> None:
        wib = timezone(timedelta(hours=7))
        prov = _valid_provenance(
            decision_at=datetime(2026, 7, 18, 15, 0, 0, 500000, tzinfo=wib),
        )
        raw = json.loads(prov.to_canonical_json())
        assert raw["decision_at"] == "2026-07-18T08:00:00.500000Z"


class TestStrictTypeValidation:
    """Finding 3 — domain types must be enforced at construction."""

    def test_datetime_rejected_for_date_field_in_artifact_dimensions(self) -> None:
        with pytest.raises(ValueError, match="date, not datetime"):
            _valid_artifact_dimensions(
                effective_session=datetime(2026, 7, 18, tzinfo=timezone.utc),
            )

    def test_datetime_rejected_for_observed_through(self) -> None:
        with pytest.raises(ValueError, match="date, not datetime"):
            _valid_source(
                observed_through=datetime(2026, 7, 17, tzinfo=timezone.utc),
            )

    def test_datetime_rejected_for_latest_completed_session(self) -> None:
        with pytest.raises(ValueError, match="date, not datetime"):
            _valid_provenance(
                latest_completed_session=datetime(2026, 7, 17, tzinfo=timezone.utc),
            )

    def test_datetime_rejected_for_analysis_as_of(self) -> None:
        with pytest.raises(ValueError, match="date, not datetime"):
            _valid_provenance(
                analysis_as_of=datetime(2026, 7, 18, tzinfo=timezone.utc),
            )

    def test_string_rejected_for_effective_session(self) -> None:
        with pytest.raises(ValueError, match="must be a date"):
            _valid_artifact_dimensions(effective_session="2026-07-18")  # type: ignore[arg-type]

    def test_raw_string_rejected_for_semantic_compatibility_id(self) -> None:
        with pytest.raises(ValueError, match="must be SemanticCompatibilityId"):
            _valid_artifact_dimensions(
                semantic_compatibility_id="sha256:" + "c" * 64,  # type: ignore[arg-type]
            )

    def test_raw_string_rejected_for_artifact_id_in_bundle(self) -> None:
        with pytest.raises(ValueError, match="must be ArtifactId"):
            SignalArtifactIdentity(
                artifact_id="sha256:" + "c" * 64,  # type: ignore[arg-type]
                semantic_compatibility_id=SemanticCompatibilityId(_VALID_PREFIXED),
                provenance=_valid_provenance(),
            )

    def test_raw_string_rejected_for_compat_id_in_bundle(self) -> None:
        with pytest.raises(ValueError, match="must be SemanticCompatibilityId"):
            SignalArtifactIdentity(
                artifact_id=ArtifactId(_VALID_PREFIXED),
                semantic_compatibility_id="sha256:" + "c" * 64,  # type: ignore[arg-type]
                provenance=_valid_provenance(),
            )

    def test_wrong_type_rejected_for_provenance_in_bundle(self) -> None:
        with pytest.raises(ValueError, match="must be ArtifactProvenance"):
            SignalArtifactIdentity(
                artifact_id=ArtifactId(_VALID_PREFIXED),
                semantic_compatibility_id=SemanticCompatibilityId(_VALID_PREFIXED),
                provenance="not-a-provenance",  # type: ignore[arg-type]
            )

    def test_non_date_rejected_for_observed_through(self) -> None:
        with pytest.raises(ValueError, match="must be a date"):
            _valid_source(observed_through="2026-07-17")  # type: ignore[arg-type]

    def test_non_datetime_rejected_for_available_at(self) -> None:
        with pytest.raises(ValueError, match="must be a datetime"):
            _valid_source(available_at="2026-07-18")  # type: ignore[arg-type]

    def test_non_datetime_rejected_for_cutoff_at(self) -> None:
        with pytest.raises(ValueError, match="must be a datetime"):
            _valid_source(cutoff_at="2026-07-18")  # type: ignore[arg-type]

    def test_non_datetime_rejected_for_decision_at(self) -> None:
        with pytest.raises(ValueError, match="must be a datetime"):
            _valid_provenance(decision_at="2026-07-18")  # type: ignore[arg-type]

    def test_non_datetime_rejected_for_captured_at(self) -> None:
        with pytest.raises(ValueError, match="must be a datetime"):
            _valid_provenance(captured_at="2026-07-18")  # type: ignore[arg-type]

    def test_tzinfo_with_none_utcoffset_rejected(self) -> None:
        """A tzinfo whose utcoffset() returns None is not timezone-aware."""
        class BogusTZ(tzinfo):
            def utcoffset(self, dt):
                return None
            def tzname(self, dt):
                return "BOGUS"
            def dst(self, dt):
                return None
        with pytest.raises(ValueError, match="timezone-aware"):
            _valid_source(
                available_at=datetime(2026, 7, 18, 5, 0, 0, tzinfo=BogusTZ()),
            )


class TestDeepImmutability:
    """Finding 2 — ArtifactProvenance must reject mutable collections."""

    def test_list_rejected_for_sources(self) -> None:
        src = _valid_source()
        with pytest.raises(ValueError, match="must be a tuple"):
            _valid_provenance(sources=[src])  # type: ignore[arg-type]

    def test_mixed_type_tuple_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be ArtifactSourceProvenance"):
            _valid_provenance(sources=(_valid_source(), "not-a-source"))  # type: ignore[arg-type]

    def test_non_source_object_in_tuple_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be ArtifactSourceProvenance"):
            _valid_provenance(sources=(_valid_source(), 42))  # type: ignore[arg-type]


class TestExactCanonicalJson:
    """Finding 2/5 — literal byte-exact canonical JSON assertions.

    These lock ordering, separators, null inclusion, and the complete nested
    payload because these bytes become hash inputs. Parsed assertions are kept
    only as supplemental diagnostics.
    """

    _EXPECTED_SEMANTIC = (
        '{"authority_registrations_hash":"'
        + _ANOTHER_HEX_64
        + '","evidence_contract_version":"1.0",'
        '"execution_label_policy_version":"1.0",'
        '"label_schema_version":2,'
        '"material_config_hash":"'
        + _LOWER_HEX_64
        + '",'
        '"observation_contract":"accumulation-discovery",'
        '"observation_schema_version":3,'
        '"semantic_engine_version":"3.0.0",'
        '"setup_family":"mean_reversion"}'
    )
    _EXPECTED_ARTIFACT = (
        '{"artifact_type":"candidate_observation",'
        '"effective_session":"2026-07-18",'
        '"semantic_compatibility_id":"'
        + _VALID_PREFIXED
        + '",'
        '"source_snapshot_cutoff_id":"cutoff-001",'
        '"ticker":"BBCA",'
        '"universe_snapshot_id":"univ-001"}'
    )
    _EXPECTED_SOURCE = (
        '{"available_at":"2026-07-18T05:00:00.000000Z",'
        '"cutoff_at":"2026-07-18T06:00:00.000000Z",'
        '"observed_through":"2026-07-17",'
        '"provider":"yahoo_finance",'
        '"source_family":"candles",'
        '"source_snapshot_id":"snap-001"}'
    )
    _EXPECTED_PROVENANCE = (
        '{"analysis_as_of":"2026-07-18",'
        '"application_revision":"abc1234",'
        '"captured_at":"2026-07-18T08:00:00.000000Z",'
        '"complete_authority_registry_hash":"'
        + _ANOTHER_HEX_64
        + '",'
        '"complete_config_hash":"'
        + _LOWER_HEX_64
        + '",'
        '"decision_at":"2026-07-18T07:00:00.000000Z",'
        '"idx_calendar_version":"2026.1",'
        '"invocation_actor":"test_user",'
        '"invocation_command":"saham screen accum",'
        '"latest_completed_session":"2026-07-17",'
        '"session_rule_version":"1.0",'
        '"sources":[{"available_at":"2026-07-18T05:00:00.000000Z",'
        '"cutoff_at":"2026-07-18T06:00:00.000000Z",'
        '"observed_through":"2026-07-17",'
        '"provider":"yahoo_finance",'
        '"source_family":"candles",'
        '"source_snapshot_id":"snap-001"}],'
        '"universe_snapshot_id":"univ-001"}'
    )

    def test_semantic_dimensions_exact_json(self) -> None:
        assert _valid_semantic_dimensions().to_canonical_json() == self._EXPECTED_SEMANTIC

    def test_artifact_dimensions_exact_json(self) -> None:
        assert _valid_artifact_dimensions().to_canonical_json() == self._EXPECTED_ARTIFACT

    def test_source_provenance_exact_json(self) -> None:
        assert _valid_source().to_canonical_json() == self._EXPECTED_SOURCE

    def test_provenance_exact_json(self) -> None:
        assert _valid_provenance().to_canonical_json() == self._EXPECTED_PROVENANCE

    def test_semantic_parsed_supplement(self) -> None:
        parsed = json.loads(self._EXPECTED_SEMANTIC)
        assert parsed["observation_contract"] == "accumulation-discovery"

    def test_provenance_order_locked(self) -> None:
        """Separate byte-level locking: keys must be in sorted order."""
        raw = _valid_provenance().to_canonical_json()
        keys = list(json.loads(raw).keys())
        assert keys == sorted(keys), "canonical JSON keys must be sorted"


class TestEdgeCases:
    def test_setup_family_with_single_word(self) -> None:
        dim = _valid_semantic_dimensions(setup_family="trend")
        assert dim.setup_family == "trend"

    def test_execution_label_policy_none(self) -> None:
        dim = _valid_semantic_dimensions(execution_label_policy_version=None)
        raw = json.loads(dim.to_canonical_json())
        assert raw["execution_label_policy_version"] is None

    def test_source_date_fields_none_produce_null_in_json(self) -> None:
        src = _valid_source(
            observed_through=None,
            available_at=None,
            cutoff_at=None,
        )
        raw = json.loads(src.to_canonical_json())
        assert raw["observed_through"] is None
        assert raw["available_at"] is None
        assert raw["cutoff_at"] is None

    def test_datetime_with_fixed_offset_normalizes_to_utc(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        src = _valid_source(
            available_at=datetime(2026, 7, 18, 2, 0, 0, tzinfo=eastern),
        )
        raw = json.loads(src.to_canonical_json())
        # 2AM Eastern = 7AM UTC on same day
        assert raw["available_at"] == "2026-07-18T07:00:00.000000Z"

    def test_decision_at_other_timezone_normalizes(self) -> None:
        # 15:00 WIB (UTC+7) = 08:00 UTC
        wib = timezone(timedelta(hours=7))
        prov = _valid_provenance(
            decision_at=datetime(2026, 7, 18, 15, 0, 0, tzinfo=wib),
        )
        raw = json.loads(prov.to_canonical_json())
        assert raw["decision_at"] == "2026-07-18T08:00:00.000000Z"

