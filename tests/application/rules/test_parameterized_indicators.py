"""
Tests for parameterized indicator configuration.

Tests cover:
- IndicatorType enum parsing
- IndicatorDefinition creation and validation
- RuleSet with indicator definitions
- Built-in shadowing validation
- YAML loader parsing of indicators section
- Interpreter with string-based indicator resolution
- IndicatorSnapshot.get() method
"""

from datetime import date
from decimal import Decimal

import pytest

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
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot

# --- IndicatorType Enum Tests ---


class TestIndicatorTypeEnum:
    """Test IndicatorType enum behavior."""

    def test_from_string_valid_uppercase(self):
        """Should parse uppercase indicator type names."""
        assert IndicatorType.from_string("RSI") == IndicatorType.RSI
        assert IndicatorType.from_string("SMA") == IndicatorType.SMA
        assert IndicatorType.from_string("EMA") == IndicatorType.EMA

    def test_from_string_valid_lowercase(self):
        """Should parse lowercase indicator type names (case-insensitive)."""
        assert IndicatorType.from_string("rsi") == IndicatorType.RSI
        assert IndicatorType.from_string("sma") == IndicatorType.SMA
        assert IndicatorType.from_string("ema") == IndicatorType.EMA

    def test_from_string_strips_whitespace(self):
        """Should handle whitespace around type names."""
        assert IndicatorType.from_string("  RSI  ") == IndicatorType.RSI

    def test_from_string_invalid_raises(self):
        """Should raise ValueError for unknown types."""
        with pytest.raises(ValueError, match="Unknown indicator type 'MACD'"):
            IndicatorType.from_string("MACD")


# --- IndicatorDefinition Tests ---


class TestIndicatorDefinition:
    """Test IndicatorDefinition dataclass."""

    def test_creation_basic(self):
        """Should create a valid indicator definition."""
        definition = IndicatorDefinition(
            name="fast_ema",
            indicator_type=IndicatorType.EMA,
            period=9,
        )
        assert definition.name == "fast_ema"
        assert definition.indicator_type == IndicatorType.EMA
        assert definition.period == 9
        assert definition.override is False

    def test_creation_with_override(self):
        """Should create definition with override flag."""
        definition = IndicatorDefinition(
            name="RSI",
            indicator_type=IndicatorType.RSI,
            period=7,
            override=True,
        )
        assert definition.override is True

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        definition = IndicatorDefinition(
            name="fast_ema",
            indicator_type=IndicatorType.EMA,
            period=9,
        )
        with pytest.raises(AttributeError):
            definition.period = 20

    def test_empty_name_raises(self):
        """Should raise ValueError for empty name."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            IndicatorDefinition(
                name="",
                indicator_type=IndicatorType.EMA,
                period=9,
            )

    def test_period_zero_raises(self):
        """Should raise ValueError for period < 1."""
        with pytest.raises(ValueError, match="period must be >= 1"):
            IndicatorDefinition(
                name="fast_ema",
                indicator_type=IndicatorType.EMA,
                period=0,
            )

    def test_period_negative_raises(self):
        """Should raise ValueError for negative period."""
        with pytest.raises(ValueError, match="period must be >= 1"):
            IndicatorDefinition(
                name="fast_ema",
                indicator_type=IndicatorType.EMA,
                period=-5,
            )


# --- Built-in Indicators Constants Tests ---


class TestBuiltinIndicators:
    """Test BUILTIN_INDICATORS constant."""

    def test_contains_rsi(self):
        """RSI should be a built-in with default period 14."""
        assert "RSI" in BUILTIN_INDICATORS
        ind_type, period = BUILTIN_INDICATORS["RSI"]
        assert ind_type == IndicatorType.RSI
        assert period == 14

    def test_contains_sma(self):
        """SMA should be a built-in with default period 20."""
        assert "SMA" in BUILTIN_INDICATORS
        ind_type, period = BUILTIN_INDICATORS["SMA"]
        assert ind_type == IndicatorType.SMA
        assert period == 20

    def test_contains_ema(self):
        """EMA should be a built-in with default period 20."""
        assert "EMA" in BUILTIN_INDICATORS
        ind_type, period = BUILTIN_INDICATORS["EMA"]
        assert ind_type == IndicatorType.EMA
        assert period == 20


# --- RuleSet with Indicators Tests ---


class TestRuleSetWithIndicators:
    """Test RuleSet with indicator definitions."""

    def _make_condition(self, indicator_name: str) -> ConditionIndicatorVsValue:
        """Helper to create a test condition."""
        return ConditionIndicatorVsValue(
            indicator_name=indicator_name,
            operator=Operator.LT,
            value=Decimal("30"),
        )

    def _make_rule(self, name: str, indicator_name: str = "RSI") -> Rule:
        """Helper to create a test rule."""
        return Rule(
            name=name,
            condition=self._make_condition(indicator_name),
            outcome=Outcome.LOW_RISK,
        )

    def test_creation_without_indicators(self):
        """Should create rule set without indicator definitions (backward compat)."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
        )
        assert rule_set.indicators == ()

    def test_creation_with_indicators(self):
        """Should create rule set with indicator definitions."""
        indicators = (
            IndicatorDefinition("fast_ema", IndicatorType.EMA, 9),
            IndicatorDefinition("slow_ema", IndicatorType.EMA, 21),
        )
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1", "fast_ema"),),
            indicators=indicators,
        )
        assert len(rule_set.indicators) == 2

    def test_duplicate_indicator_names_raises(self):
        """Should raise ValueError for duplicate indicator names."""
        indicators = (
            IndicatorDefinition("fast_ema", IndicatorType.EMA, 9),
            IndicatorDefinition("fast_ema", IndicatorType.EMA, 12),  # Duplicate
        )
        with pytest.raises(ValueError, match="Indicator names must be unique.*'fast_ema'"):
            RuleSet(
                version=1,
                name="test_rules",
                default_outcome=Outcome.MODERATE,
                rules=(self._make_rule("rule1", "fast_ema"),),
                indicators=indicators,
            )

    def test_builtin_shadowing_without_override_raises(self):
        """Should raise ValueError when shadowing built-in without override."""
        indicators = (IndicatorDefinition("RSI", IndicatorType.RSI, 7),)  # Shadows built-in
        with pytest.raises(ValueError, match="shadows built-in"):
            RuleSet(
                version=1,
                name="test_rules",
                default_outcome=Outcome.MODERATE,
                rules=(self._make_rule("rule1", "RSI"),),
                indicators=indicators,
            )

    def test_builtin_shadowing_with_override_ok(self):
        """Should allow shadowing built-in with override=True."""
        indicators = (IndicatorDefinition("RSI", IndicatorType.RSI, 7, override=True),)
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1", "RSI"),),
            indicators=indicators,
        )
        assert len(rule_set.indicators) == 1

    def test_get_indicator_definition_found(self):
        """Should return definition when found."""
        definition = IndicatorDefinition("fast_ema", IndicatorType.EMA, 9)
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1", "fast_ema"),),
            indicators=(definition,),
        )
        result = rule_set.get_indicator_definition("fast_ema")
        assert result == definition

    def test_get_indicator_definition_not_found(self):
        """Should return None when not found."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
        )
        assert rule_set.get_indicator_definition("fast_ema") is None

    def test_get_all_referenced_indicators_single(self):
        """Should collect indicator names from indicator-vs-value condition."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1", "RSI"),),
        )
        refs = rule_set.get_all_referenced_indicators()
        assert refs == {"RSI"}

    def test_get_all_referenced_indicators_indicator_vs_indicator(self):
        """Should collect indicator names from indicator-vs-indicator condition."""
        condition = ConditionIndicatorVsIndicator(
            left=IndicatorRef(name="fast_ema"),
            operator=Operator.GT,
            right=IndicatorRef(name="slow_ema"),
        )
        rule = Rule(
            name="crossover",
            condition=condition,
            outcome=Outcome.LOW_RISK,
        )
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(rule,),
            indicators=(
                IndicatorDefinition("fast_ema", IndicatorType.EMA, 9),
                IndicatorDefinition("slow_ema", IndicatorType.EMA, 21),
            ),
        )
        refs = rule_set.get_all_referenced_indicators()
        assert refs == {"fast_ema", "slow_ema"}

    def test_is_indicator_defined_custom(self):
        """Should return True for custom defined indicator."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1", "fast_ema"),),
            indicators=(IndicatorDefinition("fast_ema", IndicatorType.EMA, 9),),
        )
        assert rule_set.is_indicator_defined("fast_ema") is True

    def test_is_indicator_defined_builtin(self):
        """Should return True for built-in indicator."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
        )
        assert rule_set.is_indicator_defined("RSI") is True
        assert rule_set.is_indicator_defined("SMA") is True
        assert rule_set.is_indicator_defined("EMA") is True

    def test_is_indicator_defined_unknown(self):
        """Should return False for unknown indicator."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
        )
        assert rule_set.is_indicator_defined("unknown") is False


# --- IndicatorSnapshot Tests ---


class TestIndicatorSnapshotExtras:
    """Test IndicatorSnapshot extras field and get() method."""

    def test_creation_without_extras(self):
        """Should create snapshot without extras (backward compat)."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
        )
        assert snapshot.extras == ()

    def test_creation_with_extras(self):
        """Should create snapshot with extras."""
        extras = (
            ("fast_ema", Decimal("99")),
            ("slow_ema", Decimal("102")),
        )
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
            extras=extras,
        )
        assert len(snapshot.extras) == 2

    def test_get_builtin_rsi(self):
        """Should retrieve RSI via get()."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
        )
        assert snapshot.get("RSI") == Decimal("55")

    def test_get_builtin_sma(self):
        """Should retrieve SMA via get()."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
        )
        assert snapshot.get("SMA") == Decimal("100")

    def test_get_builtin_ema(self):
        """Should retrieve EMA via get()."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
        )
        assert snapshot.get("EMA") == Decimal("101")

    def test_get_custom_indicator(self):
        """Should retrieve custom indicator from extras."""
        extras = (
            ("fast_ema", Decimal("99")),
            ("slow_ema", Decimal("102")),
        )
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
            extras=extras,
        )
        assert snapshot.get("fast_ema") == Decimal("99")
        assert snapshot.get("slow_ema") == Decimal("102")

    def test_get_unknown_raises_keyerror(self):
        """Should raise KeyError for unknown indicator."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
        )
        with pytest.raises(KeyError, match="'unknown' not found"):
            snapshot.get("unknown")

    def test_with_extras_creates_new_snapshot(self):
        """Should create new snapshot with combined extras."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("101"),
            rsi=Decimal("55"),
            extras=(("fast_ema", Decimal("99")),),
        )
        new_snapshot = snapshot.with_extras((("slow_ema", Decimal("102")),))

        # Original unchanged
        assert len(snapshot.extras) == 1

        # New has combined extras
        assert len(new_snapshot.extras) == 2
        assert new_snapshot.get("fast_ema") == Decimal("99")
        assert new_snapshot.get("slow_ema") == Decimal("102")


# --- IndicatorRef Tests ---


class TestIndicatorRef:
    """Test IndicatorRef with string-based name."""

    def test_creation_with_custom_name(self):
        """Should create ref with custom indicator name."""
        ref = IndicatorRef(name="fast_ema")
        assert ref.name == "fast_ema"

    def test_creation_with_builtin_name(self):
        """Should create ref with built-in indicator name."""
        ref = IndicatorRef(name="RSI")
        assert ref.name == "RSI"

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        ref = IndicatorRef(name="fast_ema")
        with pytest.raises(AttributeError):
            ref.name = "slow_ema"


# --- Condition Tests with String Names ---


class TestConditionsWithStringNames:
    """Test condition classes with string-based indicator names."""

    def test_indicator_vs_value_with_custom_name(self):
        """Should create condition with custom indicator name."""
        condition = ConditionIndicatorVsValue(
            indicator_name="rsi_short",
            operator=Operator.LT,
            value=Decimal("25"),
        )
        assert condition.indicator_name == "rsi_short"

    def test_indicator_vs_value_with_builtin_name(self):
        """Should create condition with built-in indicator name."""
        condition = ConditionIndicatorVsValue(
            indicator_name="RSI",
            operator=Operator.LT,
            value=Decimal("30"),
        )
        assert condition.indicator_name == "RSI"

    def test_indicator_vs_indicator_with_custom_names(self):
        """Should create condition with custom indicator names."""
        condition = ConditionIndicatorVsIndicator(
            left=IndicatorRef(name="fast_ema"),
            operator=Operator.GT,
            right=IndicatorRef(name="slow_ema"),
        )
        assert condition.left.name == "fast_ema"
        assert condition.right.name == "slow_ema"
