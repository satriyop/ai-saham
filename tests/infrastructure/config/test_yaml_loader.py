"""
Tests for YamlConfigLoader.

Tests cover:
- Valid file loading
- File not found errors
- Invalid YAML syntax
- Missing required fields
- Unknown indicators/operators/outcomes
- Duplicate rule names
- Both condition types
"""

import tempfile
from pathlib import Path

import pytest

from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
from src.application.rules.schema import (
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    Operator,
    Outcome,
)
from src.infrastructure.config.yaml_loader import YamlConfigLoader

# --- Test Fixtures ---


def write_yaml(content: str) -> Path:
    """Write YAML content to a temporary file and return the path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        return Path(f.name)


VALID_YAML = """
version: 1
name: test_rules
default_outcome: MODERATE

rules:
  - name: oversold
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
"""

VALID_YAML_FULL = """
version: 1
name: full_test
description: A comprehensive test rule set
default_outcome: HIGH_RISK

rules:
  - name: oversold
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: RSI indicates oversold

  - name: bullish_crossover
    priority: 20
    when:
      left:
        indicator: EMA
      operator: ">"
      right:
        indicator: SMA
    outcome: LOW_RISK
    rationale: Bullish trend detected
"""


# --- Valid File Tests ---


class TestValidFileLoading:
    """Test loading valid YAML files."""

    def test_load_minimal_valid_yaml(self):
        """Should load a minimal valid YAML file."""
        path = write_yaml(VALID_YAML)
        try:
            rule_set = YamlConfigLoader.load(path)

            assert rule_set.version == 1
            assert rule_set.name == "test_rules"
            assert rule_set.default_outcome == Outcome.MODERATE
            assert len(rule_set.rules) == 1
        finally:
            path.unlink()

    def test_load_full_valid_yaml(self):
        """Should load a complete YAML file with all features."""
        path = write_yaml(VALID_YAML_FULL)
        try:
            rule_set = YamlConfigLoader.load(path)

            assert rule_set.version == 1
            assert rule_set.name == "full_test"
            assert rule_set.description == "A comprehensive test rule set"
            assert rule_set.default_outcome == Outcome.HIGH_RISK
            assert len(rule_set.rules) == 2
        finally:
            path.unlink()

    def test_load_indicator_vs_value_condition(self):
        """Should correctly parse indicator-vs-value conditions."""
        path = write_yaml(VALID_YAML)
        try:
            rule_set = YamlConfigLoader.load(path)
            rule = rule_set.rules[0]

            assert isinstance(rule.condition, ConditionIndicatorVsValue)
            assert rule.condition.indicator_name == "RSI"
            assert rule.condition.operator == Operator.LT
            assert rule.condition.value == 30
        finally:
            path.unlink()

    def test_load_indicator_vs_indicator_condition(self):
        """Should correctly parse indicator-vs-indicator conditions."""
        path = write_yaml(VALID_YAML_FULL)
        try:
            rule_set = YamlConfigLoader.load(path)
            rule = rule_set.rules[1]

            assert isinstance(rule.condition, ConditionIndicatorVsIndicator)
            assert rule.condition.left.name == "EMA"
            assert rule.condition.operator == Operator.GT
            assert rule.condition.right.name == "SMA"
        finally:
            path.unlink()

    def test_load_with_string_path(self):
        """Should accept string path in addition to Path object."""
        path = write_yaml(VALID_YAML)
        try:
            rule_set = YamlConfigLoader.load(str(path))
            assert rule_set.name == "test_rules"
        finally:
            path.unlink()

    def test_load_priority_values(self):
        """Should correctly load priority values."""
        path = write_yaml(VALID_YAML_FULL)
        try:
            rule_set = YamlConfigLoader.load(path)

            assert rule_set.rules[0].priority == 10
            assert rule_set.rules[1].priority == 20
        finally:
            path.unlink()

    def test_load_default_priority(self):
        """Should use default priority when not specified."""
        path = write_yaml(VALID_YAML)
        try:
            rule_set = YamlConfigLoader.load(path)

            assert rule_set.rules[0].priority == 100  # default
        finally:
            path.unlink()

    def test_load_all_operators(self):
        """Should correctly load all operators."""
        yaml_content = """
version: 1
name: operator_test
default_outcome: MODERATE

rules:
  - name: lt
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
  - name: le
    when: {indicator: RSI, operator: "<=", value: 30}
    outcome: LOW_RISK
  - name: gt
    when: {indicator: RSI, operator: ">", value: 70}
    outcome: HIGH_RISK
  - name: ge
    when: {indicator: RSI, operator: ">=", value: 70}
    outcome: HIGH_RISK
  - name: eq
    when: {indicator: RSI, operator: "==", value: 50}
    outcome: MODERATE
  - name: ne
    when: {indicator: RSI, operator: "!=", value: 50}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            rule_set = YamlConfigLoader.load(path)

            operators = [r.condition.operator for r in rule_set.rules]
            assert Operator.LT in operators
            assert Operator.LE in operators
            assert Operator.GT in operators
            assert Operator.GE in operators
            assert Operator.EQ in operators
            assert Operator.NE in operators
        finally:
            path.unlink()


# --- File Error Tests ---


class TestFileErrors:
    """Test file-related errors."""

    def test_file_not_found(self):
        """Should raise RulesFileError when file doesn't exist."""
        with pytest.raises(RulesFileError, match="not found"):
            YamlConfigLoader.load("/nonexistent/path/rules.yaml")

    def test_directory_instead_of_file(self):
        """Should raise appropriate error for directory path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RulesFileError):
                YamlConfigLoader.load(tmpdir)


# --- YAML Syntax Error Tests ---


class TestYamlSyntaxErrors:
    """Test YAML syntax error handling."""

    def test_invalid_yaml_syntax(self):
        """Should raise RulesSchemaError for invalid YAML."""
        invalid_yaml = """
version: 1
name: test
  bad_indent: here
"""
        path = write_yaml(invalid_yaml)
        try:
            with pytest.raises(RulesSchemaError, match="Invalid YAML"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_empty_file(self):
        """Should raise RulesSchemaError for empty file."""
        path = write_yaml("")
        try:
            with pytest.raises(RulesSchemaError, match="Empty"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_non_mapping_root(self):
        """Should raise RulesSchemaError if root is not a mapping."""
        path = write_yaml("- just\n- a\n- list")
        try:
            with pytest.raises(RulesSchemaError, match="must be a YAML mapping"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()


# --- Missing Field Tests ---


class TestMissingFields:
    """Test missing required field handling."""

    def test_missing_version(self):
        """Should raise RulesSchemaError for missing version."""
        yaml_content = """
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'version'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_missing_name(self):
        """Should raise RulesSchemaError for missing name."""
        yaml_content = """
version: 1
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'name'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_missing_default_outcome(self):
        """Should raise RulesSchemaError for missing default_outcome."""
        yaml_content = """
version: 1
name: test
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'default_outcome'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_missing_rules(self):
        """Should raise RulesSchemaError for missing rules."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'rules'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_empty_rules_list(self):
        """Should raise RulesSchemaError for empty rules list."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules: []
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="at least one rule"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_missing_rule_name(self):
        """Should raise RulesSchemaError for rule missing name."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'name'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_missing_rule_when(self):
        """Should raise RulesSchemaError for rule missing when."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'when'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_missing_rule_outcome(self):
        """Should raise RulesSchemaError for rule missing outcome."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="missing required field 'outcome'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()


# --- Validation Error Tests ---


class TestValidationErrors:
    """Test validation error handling."""

    def test_unknown_indicator(self):
        """Should raise RulesValidationError for unknown indicator."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: MACD, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesValidationError, match="undefined indicator 'MACD'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_unknown_operator(self):
        """Should raise RulesValidationError for unknown operator."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "~", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesValidationError, match="Unknown operator '~'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_unknown_outcome(self):
        """Should raise RulesValidationError for unknown outcome."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: BUY
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesValidationError, match="Unknown outcome 'BUY'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_unknown_default_outcome(self):
        """Should raise RulesValidationError for unknown default_outcome."""
        yaml_content = """
version: 1
name: test
default_outcome: NEUTRAL
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesValidationError, match="Unknown outcome 'NEUTRAL'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_duplicate_rule_names(self):
        """Should raise RulesValidationError for duplicate rule names."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: same_name
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
  - name: same_name
    when: {indicator: RSI, operator: ">", value: 70}
    outcome: HIGH_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesValidationError, match="Duplicate: 'same_name'"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_unsupported_version(self):
        """Should raise RulesSchemaError for unsupported version."""
        yaml_content = """
version: 2
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="Unsupported version 2"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_invalid_priority_type(self):
        """Should raise RulesValidationError for non-integer priority."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    priority: "high"
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesValidationError, match="priority: must be an integer"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_invalid_condition_structure(self):
        """Should raise RulesSchemaError for invalid condition structure."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {foo: bar}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="must have either"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()


# --- Type Error Tests ---


class TestTypeErrors:
    """Test type validation."""

    def test_version_wrong_type(self):
        """Should raise RulesSchemaError for non-integer version."""
        yaml_content = """
version: "one"
name: test
default_outcome: MODERATE
rules:
  - name: test
    when: {indicator: RSI, operator: "<", value: 30}
    outcome: LOW_RISK
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="expected int, got str"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_rules_wrong_type(self):
        """Should raise RulesSchemaError for non-list rules."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules: "not a list"
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="expected list, got str"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()

    def test_rule_wrong_type(self):
        """Should raise RulesSchemaError for non-mapping rule."""
        yaml_content = """
version: 1
name: test
default_outcome: MODERATE
rules:
  - "just a string"
"""
        path = write_yaml(yaml_content)
        try:
            with pytest.raises(RulesSchemaError, match="rule must be a mapping"):
                YamlConfigLoader.load(path)
        finally:
            path.unlink()


class TestRulesYamlLoaderCompatibility:
    """Test compatibility of RulesYamlLoader import and usage."""

    def test_rules_yaml_loader_equivalence(self):
        """Should import RulesYamlLoader and verify load_from_string has same behavior."""
        from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader

        rules_from_string_old = YamlConfigLoader.load_from_string(VALID_YAML)
        rules_from_string_new = RulesYamlLoader.load_from_string(VALID_YAML)

        assert RulesYamlLoader is YamlConfigLoader
        assert rules_from_string_new.name == rules_from_string_old.name
        assert len(rules_from_string_new.rules) == len(rules_from_string_old.rules)
        assert rules_from_string_new.rules[0].name == rules_from_string_old.rules[0].name
