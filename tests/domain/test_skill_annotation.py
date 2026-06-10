"""
Tests for skill annotation value objects.

Tests verify:
- ArtifactType enum values
- SkillAnnotation creation, validation, and immutability
- DriftInfo creation and fields
- SkillMetadata creation and structure

Layer: Domain
"""

from pathlib import Path

import pytest

from src.domain.value_objects.skill_annotation import (
    ArtifactType,
    DriftInfo,
    SkillAnnotation,
    SkillMetadata,
)


class TestArtifactType:
    """Test ArtifactType enum."""

    def test_enum_has_strategy_value(self):
        """ArtifactType should have STRATEGY member."""
        assert ArtifactType.STRATEGY.value == "strategy"

    def test_enum_has_indicator_value(self):
        """ArtifactType should have INDICATOR member."""
        assert ArtifactType.INDICATOR.value == "indicator"

    def test_enum_has_formula_value(self):
        """ArtifactType should have FORMULA member."""
        assert ArtifactType.FORMULA.value == "formula"


class TestSkillAnnotation:
    """Test SkillAnnotation value object."""

    def test_create_with_all_fields(self):
        """SkillAnnotation should accept all fields."""
        annotation = SkillAnnotation(
            description="Test description",
            when_to_use="When testing",
            tags=("tag1", "tag2"),
            limitations=("limitation1",),
            examples=("example1", "example2"),
        )

        assert annotation.description == "Test description"
        assert annotation.when_to_use == "When testing"
        assert annotation.tags == ("tag1", "tag2")
        assert annotation.limitations == ("limitation1",)
        assert annotation.examples == ("example1", "example2")

    def test_create_with_required_fields_only(self):
        """SkillAnnotation should work with only required fields."""
        annotation = SkillAnnotation(
            description="Test description",
            when_to_use="When testing",
        )

        assert annotation.description == "Test description"
        assert annotation.when_to_use == "When testing"
        assert annotation.tags == ()
        assert annotation.limitations == ()
        assert annotation.examples == ()

    def test_default_optional_fields_are_empty_tuples(self):
        """Optional fields should default to empty tuples."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
        )

        assert isinstance(annotation.tags, tuple)
        assert isinstance(annotation.limitations, tuple)
        assert isinstance(annotation.examples, tuple)
        assert len(annotation.tags) == 0
        assert len(annotation.limitations) == 0
        assert len(annotation.examples) == 0

    def test_empty_description_raises_error(self):
        """Empty description should raise ValueError."""
        with pytest.raises(ValueError, match="description must not be empty"):
            SkillAnnotation(
                description="",
                when_to_use="When testing",
            )

    def test_whitespace_only_description_raises_error(self):
        """Whitespace-only description should raise ValueError."""
        with pytest.raises(ValueError, match="description must not be empty"):
            SkillAnnotation(
                description="   ",
                when_to_use="When testing",
            )

    def test_empty_when_to_use_raises_error(self):
        """Empty when_to_use should raise ValueError."""
        with pytest.raises(ValueError, match="when_to_use must not be empty"):
            SkillAnnotation(
                description="Test description",
                when_to_use="",
            )

    def test_whitespace_only_when_to_use_raises_error(self):
        """Whitespace-only when_to_use should raise ValueError."""
        with pytest.raises(ValueError, match="when_to_use must not be empty"):
            SkillAnnotation(
                description="Test description",
                when_to_use="   ",
            )

    def test_is_frozen_immutable(self):
        """SkillAnnotation should be immutable (frozen dataclass)."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
        )

        with pytest.raises(AttributeError):
            annotation.description = "Modified"

        with pytest.raises(AttributeError):
            annotation.tags = ("new_tag",)


class TestDriftInfo:
    """Test DriftInfo value object."""

    def test_create_with_all_fields(self):
        """DriftInfo should accept all fields."""
        drift = DriftInfo(
            rules_hash="abc123",
            is_stale=True,
            stored_hash="def456",
        )

        assert drift.rules_hash == "abc123"
        assert drift.is_stale is True
        assert drift.stored_hash == "def456"

    def test_create_with_stored_hash_none(self):
        """DriftInfo should allow None for stored_hash."""
        drift = DriftInfo(
            rules_hash="abc123",
            is_stale=False,
            stored_hash=None,
        )

        assert drift.rules_hash == "abc123"
        assert drift.is_stale is False
        assert drift.stored_hash is None

    def test_is_stale_flag(self):
        """is_stale should correctly indicate staleness."""
        stale = DriftInfo(
            rules_hash="new_hash",
            is_stale=True,
            stored_hash="old_hash",
        )
        fresh = DriftInfo(
            rules_hash="same_hash",
            is_stale=False,
            stored_hash="same_hash",
        )

        assert stale.is_stale is True
        assert fresh.is_stale is False

    def test_is_frozen_immutable(self):
        """DriftInfo should be immutable (frozen dataclass)."""
        drift = DriftInfo(
            rules_hash="abc123",
            is_stale=False,
            stored_hash=None,
        )

        with pytest.raises(AttributeError):
            drift.is_stale = True


class TestSkillMetadata:
    """Test SkillMetadata value object."""

    def test_create_with_all_fields(self):
        """SkillMetadata should accept all fields."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
        )
        drift = DriftInfo(
            rules_hash="abc123",
            is_stale=False,
            stored_hash=None,
        )

        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test Strategy",
            artifact_path=Path("/test/strategy.yaml"),
            annotation=annotation,
            cli_usage=("saham test",),
            dependencies=("RSI", "SMA"),
            data_requirements=("ohlcv", "broker_flow"),
            rules_summary=("Rule 1: Test",),
            drift=drift,
        )

        assert metadata.artifact_type == ArtifactType.STRATEGY
        assert metadata.artifact_name == "Test Strategy"
        assert metadata.artifact_path == Path("/test/strategy.yaml")
        assert metadata.annotation == annotation
        assert metadata.cli_usage == ("saham test",)
        assert metadata.dependencies == ("RSI", "SMA")
        assert metadata.data_requirements == ("ohlcv", "broker_flow")
        assert metadata.rules_summary == ("Rule 1: Test",)
        assert metadata.drift == drift

    def test_create_with_annotation_none(self):
        """SkillMetadata should allow None annotation (missing sidecar)."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.INDICATOR,
            artifact_name="Test Indicator",
            artifact_path=Path("/test/indicator.py"),
            annotation=None,
        )

        assert metadata.annotation is None
        assert metadata.cli_usage == ()
        assert metadata.dependencies == ()
        assert metadata.data_requirements == ()
        assert metadata.rules_summary == ()
        assert metadata.drift is None

    def test_create_with_minimal_fields(self):
        """SkillMetadata should work with only required fields."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.FORMULA,
            artifact_name="SMOOTH_RSI",
            artifact_path=Path("/test/formulas.yaml"),
            annotation=None,
        )

        assert metadata.artifact_type == ArtifactType.FORMULA
        assert metadata.artifact_name == "SMOOTH_RSI"
        assert metadata.artifact_path == Path("/test/formulas.yaml")
        assert metadata.annotation is None

    def test_default_optional_fields_are_empty_tuples(self):
        """Optional tuple fields should default to empty tuples."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.INDICATOR,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
        )

        assert isinstance(metadata.cli_usage, tuple)
        assert isinstance(metadata.dependencies, tuple)
        assert isinstance(metadata.data_requirements, tuple)
        assert isinstance(metadata.rules_summary, tuple)
        assert len(metadata.cli_usage) == 0
        assert len(metadata.dependencies) == 0
        assert len(metadata.data_requirements) == 0
        assert len(metadata.rules_summary) == 0

    def test_is_frozen_immutable(self):
        """SkillMetadata should be immutable (frozen dataclass)."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
        )

        with pytest.raises(AttributeError):
            metadata.artifact_name = "Modified"

        with pytest.raises(AttributeError):
            metadata.dependencies = ("NEW_DEP",)
