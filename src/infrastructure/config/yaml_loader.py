"""
YAML configuration loader for custom rules.

Loads, parses, and validates YAML rule files, converting them to
the schema types used by the rule interpreter.

Layer: Infrastructure
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
from src.application.rules.schema import (
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    Indicator,
    IndicatorRef,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)


# Default locations to search for rules files
DEFAULT_LOCATIONS = [
    Path.home() / ".ai-saham" / "rules.yaml",
    Path("config") / "custom_rules.yaml",
]


class YamlConfigLoader:
    """Loads and validates YAML rule configuration files.

    Handles file reading, YAML parsing, schema validation, and
    conversion to typed schema objects. All validation errors
    are reported with clear, actionable messages.

    This is a pure infrastructure adapter with no business logic.
    """

    @classmethod
    def load(cls, path: Path | str | None = None) -> RuleSet:
        """Load a YAML rules file and return a validated RuleSet.

        Args:
            path: Path to the YAML file. If None, searches default locations.

        Returns:
            Validated RuleSet ready for interpretation

        Raises:
            RulesFileError: If file not found or cannot be read
            RulesSchemaError: If YAML syntax is invalid or structure is wrong
            RulesValidationError: If rule content is invalid
        """
        resolved_path = cls._resolve_path(path)
        raw_content = cls._read_file(resolved_path)
        parsed_yaml = cls._parse_yaml(raw_content, resolved_path)
        return cls._build_rule_set(parsed_yaml, resolved_path)

    @classmethod
    def _resolve_path(cls, path: Path | str | None) -> Path:
        """Resolve the path to the rules file.

        Args:
            path: Explicit path or None for default search

        Returns:
            Resolved Path object

        Raises:
            RulesFileError: If no file found
        """
        if path is not None:
            resolved = Path(path)
            if not resolved.exists():
                raise RulesFileError(f"Rules file not found: {resolved}")
            return resolved

        # Search default locations
        for default_path in DEFAULT_LOCATIONS:
            if default_path.exists():
                return default_path

        locations = ", ".join(str(p) for p in DEFAULT_LOCATIONS)
        raise RulesFileError(
            f"No rules file found in default locations: {locations}"
        )

    @classmethod
    def _read_file(cls, path: Path) -> str:
        """Read file contents.

        Args:
            path: Path to read

        Returns:
            File contents as string

        Raises:
            RulesFileError: If file cannot be read
        """
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            raise RulesFileError(f"Permission denied reading: {path}")
        except OSError as e:
            raise RulesFileError(f"Error reading {path}: {e}")

    @classmethod
    def _parse_yaml(cls, content: str, path: Path) -> dict[str, Any]:
        """Parse YAML content.

        Args:
            content: YAML string content
            path: Path for error messages

        Returns:
            Parsed YAML as dictionary

        Raises:
            RulesSchemaError: If YAML syntax is invalid
        """
        try:
            parsed = yaml.safe_load(content)
            if parsed is None:
                raise RulesSchemaError(f"Empty rules file: {path}")
            if not isinstance(parsed, dict):
                raise RulesSchemaError(
                    f"Rules file must be a YAML mapping, got {type(parsed).__name__}"
                )
            return parsed
        except yaml.YAMLError as e:
            raise RulesSchemaError(f"Invalid YAML syntax in {path}: {e}")

    @classmethod
    def _build_rule_set(cls, data: dict[str, Any], path: Path) -> RuleSet:
        """Build a RuleSet from parsed YAML data.

        Args:
            data: Parsed YAML dictionary
            path: Path for error messages

        Returns:
            Validated RuleSet

        Raises:
            RulesSchemaError: If required fields missing or wrong type
            RulesValidationError: If rule content is invalid
        """
        # Validate required top-level fields
        cls._require_field(data, "version", int, "top-level")
        cls._require_field(data, "name", str, "top-level")
        cls._require_field(data, "default_outcome", str, "top-level")
        cls._require_field(data, "rules", list, "top-level")

        version = data["version"]
        if version != 1:
            raise RulesSchemaError(
                f"Unsupported version {version}. Only version 1 is supported."
            )

        name = data["name"]
        description = data.get("description")

        # Parse default_outcome
        try:
            default_outcome = Outcome.from_string(data["default_outcome"])
        except ValueError as e:
            raise RulesValidationError(f"default_outcome: {e}")

        # Parse rules
        rules_data = data["rules"]
        if not rules_data:
            raise RulesSchemaError("rules: must contain at least one rule")

        rules = []
        for i, rule_data in enumerate(rules_data):
            try:
                rule = cls._build_rule(rule_data, i)
                rules.append(rule)
            except (RulesSchemaError, RulesValidationError) as e:
                raise type(e)(f"rules[{i}]: {e}")

        try:
            return RuleSet(
                version=version,
                name=name,
                default_outcome=default_outcome,
                rules=tuple(rules),
                description=description,
            )
        except ValueError as e:
            raise RulesValidationError(str(e))

    @classmethod
    def _build_rule(cls, data: dict[str, Any], index: int) -> Rule:
        """Build a Rule from parsed YAML data.

        Args:
            data: Rule dictionary from YAML
            index: Rule index for error messages

        Returns:
            Validated Rule

        Raises:
            RulesSchemaError: If required fields missing or wrong type
            RulesValidationError: If rule content is invalid
        """
        if not isinstance(data, dict):
            raise RulesSchemaError(f"rule must be a mapping, got {type(data).__name__}")

        cls._require_field(data, "name", str, "rule")
        cls._require_field(data, "when", dict, "rule")
        cls._require_field(data, "outcome", str, "rule")

        name = data["name"]
        rationale = data.get("rationale")
        priority = data.get("priority", 100)

        if not isinstance(priority, int):
            raise RulesValidationError(f"priority: must be an integer, got {type(priority).__name__}")

        # Parse outcome
        try:
            outcome = Outcome.from_string(data["outcome"])
        except ValueError as e:
            raise RulesValidationError(f"outcome: {e}")

        # Parse condition
        condition = cls._build_condition(data["when"])

        return Rule(
            name=name,
            condition=condition,
            outcome=outcome,
            priority=priority,
            rationale=rationale,
        )

    @classmethod
    def _build_condition(
        cls, data: dict[str, Any]
    ) -> ConditionIndicatorVsValue | ConditionIndicatorVsIndicator:
        """Build a Condition from parsed YAML data.

        Detects condition type based on fields present:
        - indicator + value: ConditionIndicatorVsValue
        - left + right: ConditionIndicatorVsIndicator

        Args:
            data: Condition dictionary from YAML

        Returns:
            Validated Condition

        Raises:
            RulesSchemaError: If required fields missing or wrong type
            RulesValidationError: If condition content is invalid
        """
        # Check for indicator-vs-value condition
        if "indicator" in data and "value" in data:
            return cls._build_indicator_vs_value(data)

        # Check for indicator-vs-indicator condition
        if "left" in data and "right" in data:
            return cls._build_indicator_vs_indicator(data)

        raise RulesSchemaError(
            "when: must have either (indicator + operator + value) "
            "or (left + operator + right)"
        )

    @classmethod
    def _build_indicator_vs_value(
        cls, data: dict[str, Any]
    ) -> ConditionIndicatorVsValue:
        """Build an indicator-vs-value condition.

        Args:
            data: Condition dictionary

        Returns:
            ConditionIndicatorVsValue

        Raises:
            RulesSchemaError: If fields missing
            RulesValidationError: If content invalid
        """
        cls._require_field(data, "indicator", str, "when")
        cls._require_field(data, "operator", str, "when")
        # value can be int, float, or str

        try:
            indicator = Indicator.from_string(data["indicator"])
        except ValueError as e:
            raise RulesValidationError(f"when.indicator: {e}")

        try:
            operator = Operator.from_string(data["operator"])
        except ValueError as e:
            raise RulesValidationError(f"when.operator: {e}")

        try:
            value = Decimal(str(data["value"]))
        except (InvalidOperation, TypeError) as e:
            raise RulesValidationError(
                f"when.value: must be a number, got '{data['value']}'"
            )

        return ConditionIndicatorVsValue(
            indicator=indicator,
            operator=operator,
            value=value,
        )

    @classmethod
    def _build_indicator_vs_indicator(
        cls, data: dict[str, Any]
    ) -> ConditionIndicatorVsIndicator:
        """Build an indicator-vs-indicator condition.

        Args:
            data: Condition dictionary

        Returns:
            ConditionIndicatorVsIndicator

        Raises:
            RulesSchemaError: If fields missing
            RulesValidationError: If content invalid
        """
        cls._require_field(data, "left", dict, "when")
        cls._require_field(data, "operator", str, "when")
        cls._require_field(data, "right", dict, "when")

        try:
            operator = Operator.from_string(data["operator"])
        except ValueError as e:
            raise RulesValidationError(f"when.operator: {e}")

        left_data = data["left"]
        right_data = data["right"]

        cls._require_field(left_data, "indicator", str, "when.left")
        cls._require_field(right_data, "indicator", str, "when.right")

        try:
            left_indicator = Indicator.from_string(left_data["indicator"])
        except ValueError as e:
            raise RulesValidationError(f"when.left.indicator: {e}")

        try:
            right_indicator = Indicator.from_string(right_data["indicator"])
        except ValueError as e:
            raise RulesValidationError(f"when.right.indicator: {e}")

        return ConditionIndicatorVsIndicator(
            left=IndicatorRef(indicator=left_indicator),
            operator=operator,
            right=IndicatorRef(indicator=right_indicator),
        )

    @classmethod
    def _require_field(
        cls,
        data: dict[str, Any],
        field: str,
        expected_type: type,
        context: str,
    ) -> None:
        """Validate that a required field exists and has correct type.

        Args:
            data: Dictionary to check
            field: Field name to require
            expected_type: Expected type of the field
            context: Context for error messages (e.g., "rule", "when")

        Raises:
            RulesSchemaError: If field missing or wrong type
        """
        if field not in data:
            raise RulesSchemaError(f"{context}: missing required field '{field}'")

        value = data[field]
        if not isinstance(value, expected_type):
            raise RulesSchemaError(
                f"{context}.{field}: expected {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
