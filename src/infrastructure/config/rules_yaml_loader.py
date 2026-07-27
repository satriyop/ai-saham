"""
YAML configuration loader for custom rules.

Loads, parses, and validates YAML rule files, converting them to
the schema types used by the rule interpreter.

Layer: Infrastructure
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from src.application.ports.rules_loader import RulesLoader
from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
from src.application.rules.schema import Outcome, Rule, RuleSet
from src.infrastructure.config.rules_condition_parser import build_rule_condition
from src.infrastructure.config.rules_indicator_parser import (
    build_rule_indicators,
    validate_indicator_references,
)
from src.infrastructure.config.rules_parser_helpers import require_field
from src.infrastructure.config.rules_signal_mapping_parser import build_signal_mapping

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry


# Default locations to search for rules files
DEFAULT_LOCATIONS = [
    Path("config") / "custom_rules.yaml",
]


class RulesYamlLoader(RulesLoader):
    """Loads and validates YAML rule configuration files.

    Handles file reading, YAML parsing, schema validation, and
    conversion to typed schema objects. All validation errors
    are reported with clear, actionable messages.

    This is a pure infrastructure adapter with no business logic.
    """

    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
        registry: "IndicatorRegistry | None" = None,
    ) -> RuleSet:
        """Load a YAML rules file and return a validated RuleSet.

        Args:
            path: Path to the YAML file. If None, searches default locations.
            registry: Optional IndicatorRegistry for validating indicator references.
                     If provided, indicators registered in the registry (formulas,
                     plugins) are also considered valid references.

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
        return cls._build_rule_set(parsed_yaml, resolved_path, registry=registry)

    @classmethod
    def load_from_string(
        cls,
        content: str,
        registry: "IndicatorRegistry | None" = None,
        source_name: str = "<generated>",
    ) -> RuleSet:
        """Load a RuleSet from YAML string content.

        Useful for validating AI-generated strategy YAML before saving.

        Args:
            content: YAML string content to parse.
            registry: Optional IndicatorRegistry for validating indicator references.
            source_name: Source identifier for error messages (default: "<generated>").

        Returns:
            Validated RuleSet ready for interpretation

        Raises:
            RulesSchemaError: If YAML syntax is invalid or structure is wrong
            RulesValidationError: If rule content is invalid
        """
        source_path = Path(source_name)
        parsed_yaml = cls._parse_yaml(content, source_path)
        return cls._build_rule_set(parsed_yaml, source_path, registry=registry)

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
        raise RulesFileError(f"No rules file found in default locations: {locations}")

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
    def _build_rule_set(
        cls,
        data: dict[str, Any],
        path: Path,
        registry: "IndicatorRegistry | None" = None,
    ) -> RuleSet:
        """Build a RuleSet from parsed YAML data.

        Args:
            data: Parsed YAML dictionary
            path: Path for error messages
            registry: Optional IndicatorRegistry for validating indicator references

        Returns:
            Validated RuleSet

        Raises:
            RulesSchemaError: If required fields missing or wrong type
            RulesValidationError: If rule content is invalid
        """
        # Validate required top-level fields
        require_field(data, "version", int, "top-level")
        require_field(data, "name", str, "top-level")
        require_field(data, "default_outcome", str, "top-level")
        require_field(data, "rules", list, "top-level")

        version = data["version"]
        if version != 1:
            raise RulesSchemaError(f"Unsupported version {version}. Only version 1 is supported.")

        name = data["name"]
        description = data.get("description")

        # Parse default_outcome
        try:
            default_outcome = Outcome.from_string(data["default_outcome"])
        except ValueError as e:
            raise RulesValidationError(f"default_outcome: {e}")

        # Parse indicators (optional section)
        indicators_data = data.get("indicators", {})
        indicators = build_rule_indicators(indicators_data)

        # Parse signal_mapping (optional section)
        signal_mapping = None
        if "signal_mapping" in data:
            signal_mapping = build_signal_mapping(data["signal_mapping"])

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
            rule_set = RuleSet(
                version=version,
                name=name,
                default_outcome=default_outcome,
                rules=tuple(rules),
                indicators=indicators,
                description=description,
                signal_mapping=signal_mapping,
            )
        except ValueError as e:
            raise RulesValidationError(str(e))

        # Validate that all referenced indicators are defined
        validate_indicator_references(rule_set, registry=registry)

        return rule_set

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

        require_field(data, "name", str, "rule")
        require_field(data, "when", dict, "rule")
        require_field(data, "outcome", str, "rule")

        name = data["name"]
        rationale = data.get("rationale")
        priority = data.get("priority", 100)

        if not isinstance(priority, int):
            raise RulesValidationError(
                f"priority: must be an integer, got {type(priority).__name__}"
            )

        # Parse outcome
        try:
            outcome = Outcome.from_string(data["outcome"])
        except ValueError as e:
            raise RulesValidationError(f"outcome: {e}")

        # Parse condition
        condition = build_rule_condition(data["when"])

        return Rule(
            name=name,
            condition=condition,
            outcome=outcome,
            priority=priority,
            rationale=rationale,
        )


# Backward-compatible alias
YamlConfigLoader = RulesYamlLoader
