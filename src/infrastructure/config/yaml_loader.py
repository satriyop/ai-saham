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
    BUILTIN_INDICATORS,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorDefinition,
    IndicatorRef,
    IndicatorType,
    Operator,
    Outcome,
    Rule,
    RuleSet,
    SignalMapping,
)
from src.domain.value_objects.trade_action import TradeAction


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

        # Parse indicators (optional section)
        indicators_data = data.get("indicators", {})
        indicators = cls._build_indicators(indicators_data)

        # Parse signal_mapping (optional section)
        signal_mapping = None
        if "signal_mapping" in data:
            signal_mapping = cls._build_signal_mapping(data["signal_mapping"])

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
        cls._validate_indicator_references(rule_set)

        return rule_set

    @classmethod
    def _build_indicators(
        cls, indicators_data: dict[str, Any]
    ) -> tuple[IndicatorDefinition, ...]:
        """Build indicator definitions from parsed YAML data.

        Args:
            indicators_data: Dictionary mapping indicator names to their definitions

        Returns:
            Tuple of IndicatorDefinition objects

        Raises:
            RulesSchemaError: If indicator structure is invalid
            RulesValidationError: If indicator content is invalid
        """
        if not isinstance(indicators_data, dict):
            raise RulesSchemaError(
                f"indicators: expected mapping, got {type(indicators_data).__name__}"
            )

        indicators = []
        for ind_name, ind_data in indicators_data.items():
            try:
                indicator = cls._build_indicator_definition(ind_name, ind_data)
                indicators.append(indicator)
            except (RulesSchemaError, RulesValidationError) as e:
                raise type(e)(f"indicators.{ind_name}: {e}")

        return tuple(indicators)

    @classmethod
    def _build_signal_mapping(cls, data: dict[str, Any]) -> SignalMapping:
        """Build SignalMapping from parsed YAML data.

        Parses the optional signal_mapping section that maps risk levels
        to trade actions for backtesting.

        Args:
            data: Dictionary mapping outcome names to action names

        Returns:
            SignalMapping with custom or default actions

        Raises:
            RulesSchemaError: If structure is invalid
            RulesValidationError: If values are invalid
        """
        if not isinstance(data, dict):
            raise RulesSchemaError(
                f"signal_mapping: expected mapping, got {type(data).__name__}"
            )

        # Map of valid action strings to TradeAction enums
        action_map = {
            "ENTER_LONG": TradeAction.ENTER_LONG,
            "EXIT_LONG": TradeAction.EXIT_LONG,
            "HOLD": TradeAction.HOLD,
            "FLAT": TradeAction.FLAT,
        }

        # Parse each mapping with defaults
        def parse_action(key: str, default: TradeAction) -> TradeAction:
            if key not in data:
                return default
            value = data[key]
            if not isinstance(value, str):
                raise RulesSchemaError(
                    f"signal_mapping.{key}: expected string, got {type(value).__name__}"
                )
            normalized = value.upper().strip()
            if normalized not in action_map:
                valid = list(action_map.keys())
                raise RulesValidationError(
                    f"signal_mapping.{key}: '{value}' is not valid. Must be one of: {valid}"
                )
            return action_map[normalized]

        return SignalMapping(
            low_risk=parse_action("LOW_RISK", TradeAction.ENTER_LONG),
            moderate=parse_action("MODERATE", TradeAction.HOLD),
            high_risk=parse_action("HIGH_RISK", TradeAction.EXIT_LONG),
        )

    @classmethod
    def _build_indicator_definition(
        cls, name: str, data: dict[str, Any]
    ) -> IndicatorDefinition:
        """Build a single indicator definition.

        Supports three modes:
        1. Built-in indicators (SMA, EMA, RSI) with type and period
        2. Plugin indicators (ATR, VWAP, etc.) with type and period
        3. Formula-based indicators with formula expression

        Args:
            name: Indicator instance name
            data: Indicator definition dictionary

        Returns:
            IndicatorDefinition object

        Raises:
            RulesSchemaError: If required fields missing
            RulesValidationError: If values are invalid
        """
        if not isinstance(data, dict):
            raise RulesSchemaError(
                f"expected mapping, got {type(data).__name__}"
            )

        has_type = "type" in data
        has_formula = "formula" in data

        # Validate mutual exclusivity
        if has_type and has_formula:
            raise RulesSchemaError(
                "cannot have both 'type' and 'formula'. "
                "Use either type+period OR formula."
            )

        if not has_type and not has_formula:
            raise RulesSchemaError(
                "must have either 'type' (with period) or 'formula'"
            )

        # Parse override (common to both modes)
        override = data.get("override", False)
        if not isinstance(override, bool):
            raise RulesSchemaError(
                f"override: expected bool, got {type(override).__name__}"
            )

        # Formula-based indicator
        if has_formula:
            formula = data["formula"]
            if not isinstance(formula, str):
                raise RulesSchemaError(
                    f"formula: expected string, got {type(formula).__name__}"
                )

            formula = formula.strip()
            if not formula:
                raise RulesValidationError("formula: cannot be empty")

            # Period should not be specified for formula indicators
            if "period" in data:
                raise RulesSchemaError(
                    "formula indicators should not have 'period'. "
                    "Period is determined by the formula expression."
                )

            try:
                return IndicatorDefinition(
                    name=name,
                    formula=formula,
                    override=override,
                )
            except ValueError as e:
                raise RulesValidationError(str(e))

        # Type-based indicator (existing logic)
        cls._require_field(data, "period", int, "indicator")

        # Parse indicator type - try built-in first, then accept as plugin name
        type_str = data["type"].strip()
        try:
            indicator_type: IndicatorType | str = IndicatorType.from_string(type_str)
        except ValueError:
            # Not a built-in - store as string for plugin lookup
            # Plugin validation happens at runtime via IndicatorRegistry
            indicator_type = type_str.upper()

        period = data["period"]
        if period < 1:
            raise RulesValidationError(f"period: must be >= 1, got {period}")

        try:
            return IndicatorDefinition(
                name=name,
                indicator_type=indicator_type,
                period=period,
                override=override,
            )
        except ValueError as e:
            raise RulesValidationError(str(e))

    @classmethod
    def _validate_indicator_references(cls, rule_set: RuleSet) -> None:
        """Validate that all indicator references in rules are defined.

        Args:
            rule_set: The rule set to validate

        Raises:
            RulesValidationError: If any indicator reference is undefined
        """
        referenced = rule_set.get_all_referenced_indicators()
        for ref_name in referenced:
            if not rule_set.is_indicator_defined(ref_name):
                raise RulesValidationError(
                    f"Rule references undefined indicator '{ref_name}'. "
                    f"Define it in the 'indicators' section or use a built-in "
                    f"({', '.join(BUILTIN_INDICATORS.keys())})."
                )

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

        Indicator references are strings that can be either:
        - Custom defined indicators (e.g., "fast_ema", "rsi_short")
        - Built-in indicators ("RSI", "SMA", "EMA")

        Validation of references happens after all indicators are parsed.

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

        # Indicator is now a string reference (validated later)
        indicator_name = data["indicator"].strip()
        if not indicator_name:
            raise RulesValidationError("when.indicator: cannot be empty")

        try:
            operator = Operator.from_string(data["operator"])
        except ValueError as e:
            raise RulesValidationError(f"when.operator: {e}")

        try:
            value = Decimal(str(data["value"]))
        except (InvalidOperation, TypeError):
            raise RulesValidationError(
                f"when.value: must be a number, got '{data['value']}'"
            )

        return ConditionIndicatorVsValue(
            indicator_name=indicator_name,
            operator=operator,
            value=value,
        )

    @classmethod
    def _build_indicator_vs_indicator(
        cls, data: dict[str, Any]
    ) -> ConditionIndicatorVsIndicator:
        """Build an indicator-vs-indicator condition.

        Indicator references are strings that can be either:
        - Custom defined indicators (e.g., "fast_ema", "slow_ema")
        - Built-in indicators ("RSI", "SMA", "EMA")

        Validation of references happens after all indicators are parsed.

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

        # Indicator references are now strings (validated later)
        left_name = left_data["indicator"].strip()
        right_name = right_data["indicator"].strip()

        if not left_name:
            raise RulesValidationError("when.left.indicator: cannot be empty")
        if not right_name:
            raise RulesValidationError("when.right.indicator: cannot be empty")

        return ConditionIndicatorVsIndicator(
            left=IndicatorRef(name=left_name),
            operator=operator,
            right=IndicatorRef(name=right_name),
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
