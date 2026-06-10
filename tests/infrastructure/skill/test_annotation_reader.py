"""
Tests for .skill.yaml annotation reader.

Tests verify:
- read() returns None for missing files
- read() parses valid YAML with all fields
- read() parses minimal YAML (only required fields)
- read() raises AnnotationSchemaError for missing required fields
- read() raises AnnotationSchemaError for invalid YAML syntax
- read() raises AnnotationSchemaError for non-dict root
- read_formula_annotations() parses multi-formula sidecars
- read_formula_annotations() handles missing files gracefully
- read_formula_annotations() skips invalid formulas with warning

Layer: Infrastructure
"""

from pathlib import Path

import pytest

from src.infrastructure.skill.annotation_reader import (
    AnnotationReader,
    AnnotationSchemaError,
)
from src.domain.value_objects.skill_annotation import SkillAnnotation


class TestAnnotationReaderSingleArtifact:
    """Test reading single-artifact .skill.yaml files."""

    def test_read_returns_none_for_missing_file(self, tmp_path: Path):
        """read() should return None when file doesn't exist."""
        reader = AnnotationReader()
        missing_path = tmp_path / "nonexistent.skill.yaml"

        result = reader.read(missing_path)

        assert result is None

    def test_read_parses_valid_yaml_with_all_fields(self, tmp_path: Path):
        """read() should parse YAML with all annotation fields."""
        yaml_content = """
description: Test strategy for momentum trading
when_to_use: Use when RSI shows oversold conditions
tags:
  - momentum
  - technical
limitations:
  - Requires at least 14 days of data
  - May produce false signals in sideways markets
examples:
  - saham backtest BBCA --strategy test
  - saham strategy validate test
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read(sidecar_path)

        assert result is not None
        assert isinstance(result, SkillAnnotation)
        assert result.description == "Test strategy for momentum trading"
        assert result.when_to_use == "Use when RSI shows oversold conditions"
        assert result.tags == ("momentum", "technical")
        assert len(result.limitations) == 2
        assert "Requires at least 14 days" in result.limitations[0]
        assert len(result.examples) == 2

    def test_read_parses_minimal_yaml(self, tmp_path: Path):
        """read() should parse YAML with only required fields."""
        yaml_content = """
description: Minimal description
when_to_use: Minimal usage
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read(sidecar_path)

        assert result is not None
        assert result.description == "Minimal description"
        assert result.when_to_use == "Minimal usage"
        assert result.tags == ()
        assert result.limitations == ()
        assert result.examples == ()

    def test_read_strips_whitespace_from_required_fields(self, tmp_path: Path):
        """read() should strip leading/trailing whitespace."""
        yaml_content = """
description: "  Test description  "
when_to_use: "  Test usage  "
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read(sidecar_path)

        assert result is not None
        assert result.description == "Test description"
        assert result.when_to_use == "Test usage"

    def test_read_raises_error_for_missing_description(self, tmp_path: Path):
        """read() should raise AnnotationSchemaError when description is missing."""
        yaml_content = """
when_to_use: Test usage
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(AnnotationSchemaError, match="Missing required fields"):
            reader.read(sidecar_path)

    def test_read_raises_error_for_missing_when_to_use(self, tmp_path: Path):
        """read() should raise AnnotationSchemaError when when_to_use is missing."""
        yaml_content = """
description: Test description
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(AnnotationSchemaError, match="Missing required fields"):
            reader.read(sidecar_path)

    def test_read_raises_error_for_empty_description(self, tmp_path: Path):
        """read() should raise error for empty description string."""
        yaml_content = """
description: ""
when_to_use: Test usage
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(
            AnnotationSchemaError, match="'description' must be a non-empty string"
        ):
            reader.read(sidecar_path)

    def test_read_raises_error_for_whitespace_only_description(self, tmp_path: Path):
        """read() should raise error for whitespace-only description."""
        yaml_content = """
description: "   "
when_to_use: Test usage
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(
            AnnotationSchemaError, match="'description' must be a non-empty string"
        ):
            reader.read(sidecar_path)

    def test_read_raises_error_for_invalid_yaml_syntax(self, tmp_path: Path):
        """read() should raise AnnotationSchemaError for malformed YAML."""
        yaml_content = """
description: Test
when_to_use: [unclosed list
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(AnnotationSchemaError, match="Invalid YAML"):
            reader.read(sidecar_path)

    def test_read_raises_error_for_non_dict_root(self, tmp_path: Path):
        """read() should raise error when root is not a dict."""
        yaml_content = """
- item1
- item2
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(
            AnnotationSchemaError, match="Expected a mapping.*got list"
        ):
            reader.read(sidecar_path)

    def test_read_converts_non_list_tags_to_empty_tuple(
        self, tmp_path: Path, caplog
    ):
        """read() should gracefully handle non-list tags field."""
        yaml_content = """
description: Test
when_to_use: Test
tags: "not a list"
"""
        sidecar_path = tmp_path / "strategy.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read(sidecar_path)

        assert result is not None
        assert result.tags == ()
        assert "should be a list" in caplog.text


class TestAnnotationReaderMultiFormula:
    """Test reading multi-formula .skill.yaml files."""

    def test_read_formula_annotations_returns_dict_keyed_by_name(
        self, tmp_path: Path
    ):
        """read_formula_annotations() should return dict keyed by formula name."""
        yaml_content = """
SMOOTH_RSI:
  description: RSI with EMA smoothing
  when_to_use: When you need smoother RSI values

MOMENTUM_SCORE:
  description: Combined momentum indicator
  when_to_use: For multi-factor momentum strategies
  tags:
    - momentum
    - composite
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read_formula_annotations(sidecar_path)

        assert isinstance(result, dict)
        assert "SMOOTH_RSI" in result
        assert "MOMENTUM_SCORE" in result
        assert result["SMOOTH_RSI"].description == "RSI with EMA smoothing"
        assert result["MOMENTUM_SCORE"].tags == ("momentum", "composite")

    def test_read_formula_annotations_returns_empty_dict_for_missing_file(
        self, tmp_path: Path
    ):
        """read_formula_annotations() should return empty dict for missing file."""
        reader = AnnotationReader()
        missing_path = tmp_path / "nonexistent.skill.yaml"

        result = reader.read_formula_annotations(missing_path)

        assert result == {}

    def test_read_formula_annotations_skips_invalid_formulas_with_warning(
        self, tmp_path: Path, caplog
    ):
        """read_formula_annotations() should skip invalid entries and log warning."""
        yaml_content = """
VALID_FORMULA:
  description: Valid formula
  when_to_use: Always

INVALID_FORMULA:
  description: Missing when_to_use field

ANOTHER_VALID:
  description: Another valid formula
  when_to_use: Sometimes
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read_formula_annotations(sidecar_path)

        assert "VALID_FORMULA" in result
        assert "ANOTHER_VALID" in result
        assert "INVALID_FORMULA" not in result
        assert "Skipping formula 'INVALID_FORMULA'" in caplog.text

    def test_read_formula_annotations_skips_non_dict_entries(
        self, tmp_path: Path, caplog
    ):
        """read_formula_annotations() should skip non-dict formula entries."""
        yaml_content = """
VALID_FORMULA:
  description: Valid formula
  when_to_use: Always

BAD_FORMULA: "just a string"

ANOTHER_VALID:
  description: Another valid
  when_to_use: Sometimes
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()
        result = reader.read_formula_annotations(sidecar_path)

        assert "VALID_FORMULA" in result
        assert "ANOTHER_VALID" in result
        assert "BAD_FORMULA" not in result
        assert "expected mapping, got str" in caplog.text

    def test_read_formula_annotations_raises_error_for_non_dict_root(
        self, tmp_path: Path
    ):
        """read_formula_annotations() should raise error for non-dict root."""
        yaml_content = """
- not a dict
- another item
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(yaml_content, encoding="utf-8")

        reader = AnnotationReader()

        with pytest.raises(
            AnnotationSchemaError, match="Expected a mapping.*got list"
        ):
            reader.read_formula_annotations(sidecar_path)
