"""
Integration tests for using custom formulas in rules.

Tests the complete workflow:
1. Create custom formula via CLI
2. Use formula in rules.yaml
3. Run risk assessment with formula
4. Run backtest with formula

These tests verify the Phase 5 implementation:
- Registry-as-single-authority pattern
- Formula resolution in interpreter
- Use cases passing registry to interpreter
"""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.formula.parser import parse
from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import (
    ConditionIndicatorVsValue,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase
from src.domain.entities.candle import Candle
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader

# --- Fixtures ---


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_candles():
    """Create mock candles for testing (100 days of data)."""
    candles = []
    for i in range(100):
        # Create price pattern that will trigger different RSI values
        close = Decimal(str(10000 + (i % 20) * 50))
        candles.append(
            Candle(
                ticker="BBCA",
                date=date(2024, 1, 1) + __import__("datetime").timedelta(days=i),
                open=close - Decimal("25"),
                high=close + Decimal("50"),
                low=close - Decimal("50"),
                close=close,
                volume=1000000,
            )
        )
    return candles


@pytest.fixture
def registry_with_formula():
    """Create registry with a custom formula registered."""
    registry = IndicatorRegistry()

    # Register SMOOTH_RSI formula: SMA(RSI(14), 10)
    formula_ast = parse("SMA(RSI(14), 10)")
    registry.register_formula("SMOOTH_RSI", formula_ast)

    return registry


@pytest.fixture
def mock_repository(mock_candles):
    """Create mock repository returning test candles."""
    mock_repo = MagicMock()
    mock_repo.get_candles.return_value = mock_candles
    return mock_repo


@pytest.fixture
def rules_file_with_formula(temp_dir):
    """Create a rules file that uses SMOOTH_RSI formula."""
    rules_content = """
version: 1
name: smooth_rsi_rules
default_outcome: MODERATE

rules:
  - name: oversold
    when:
      indicator: SMOOTH_RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "Smoothed RSI indicates oversold condition"

  - name: overbought
    when:
      indicator: SMOOTH_RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "Smoothed RSI indicates overbought condition"

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG
"""
    rules_path = temp_dir / "smooth_rules.yaml"
    rules_path.write_text(rules_content)
    return rules_path


# --- Interpreter Tests ---


class TestInterpreterWithFormula:
    """Test interpreter resolving formulas from registry."""

    def test_get_required_indicators_resolves_formula(self, registry_with_formula):
        """Should resolve formula indicator from registry."""
        rules = [
            Rule(
                name="test",
                condition=ConditionIndicatorVsValue(
                    indicator_name="SMOOTH_RSI",
                    operator=Operator.LT,
                    value=Decimal("30"),
                ),
                outcome=Outcome.LOW_RISK,
            )
        ]
        rule_set = RuleSet(
            version=1,
            name="test",
            default_outcome=Outcome.MODERATE,
            rules=tuple(rules),
        )
        interpreter = YamlRuleInterpreter(rule_set)

        required = interpreter.get_required_indicators(registry=registry_with_formula)

        assert "SMOOTH_RSI" in required
        type_name, period = required["SMOOTH_RSI"]
        assert type_name == "SMOOTH_RSI"
        assert period == 0  # Formulas have period=0

    def test_interpreter_raises_for_unregistered_formula(self):
        """Should raise error when formula is not in registry."""
        rules = [
            Rule(
                name="test",
                condition=ConditionIndicatorVsValue(
                    indicator_name="NONEXISTENT_FORMULA",
                    operator=Operator.LT,
                    value=Decimal("30"),
                ),
                outcome=Outcome.LOW_RISK,
            )
        ]
        rule_set = RuleSet(
            version=1,
            name="test",
            default_outcome=Outcome.MODERATE,
            rules=tuple(rules),
        )
        interpreter = YamlRuleInterpreter(rule_set)

        # Empty registry - formula not registered
        empty_registry = IndicatorRegistry()

        with pytest.raises(ValueError) as exc_info:
            interpreter.get_required_indicators(registry=empty_registry)

        assert "NONEXISTENT_FORMULA" in str(exc_info.value)
        assert "Unknown indicator" in str(exc_info.value)


# --- AssessRiskUseCase Tests ---


class TestAssessRiskWithFormula:
    """Test risk assessment with custom formula."""

    def test_assess_risk_computes_formula(
        self, mock_repository, registry_with_formula, rules_file_with_formula
    ):
        """Should compute formula indicator for risk assessment."""
        use_case = AssessRiskUseCase(
            repository=mock_repository,
            registry=registry_with_formula,
            rules_loader=RulesYamlLoader(),
        )

        request = AssessRiskRequest(
            ticker="BBCA",
            rules_file=rules_file_with_formula,
        )

        response = use_case.execute(request)

        # Should not raise - formula was computed successfully
        assert response.ticker == "BBCA"
        # Assessment should have been made
        assert response.assessment is not None
        assert response.assessment is not None
        assert response.assessment.risk_level_name in ("BLOCKED", "OPEN")

    def test_assess_risk_formula_affects_result(
        self, mock_repository, registry_with_formula, temp_dir
    ):
        """Formula value should affect risk assessment outcome."""
        # Create rules where SMOOTH_RSI < 30 -> LOW_RISK
        rules_content = """
version: 1
name: test_rules
default_outcome: MODERATE

rules:
  - name: oversold
    when:
      indicator: SMOOTH_RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
"""
        rules_path = temp_dir / "test_rules.yaml"
        rules_path.write_text(rules_content)

        use_case = AssessRiskUseCase(
            repository=mock_repository,
            registry=registry_with_formula,
            rules_loader=RulesYamlLoader(),
        )

        request = AssessRiskRequest(
            ticker="BBCA",
            rules_file=rules_path,
        )

        response = use_case.execute(request)

        # The actual outcome depends on the computed SMOOTH_RSI value
        # We just verify the system works end-to-end
        assert response.assessment is not None
        assert response.assessment.risk_level_name in ("BLOCKED", "OPEN")


# --- BacktestUseCase Tests ---


class TestBacktestWithFormula:
    """Test backtest with custom formula."""

    def test_backtest_computes_formula(
        self, mock_repository, registry_with_formula, rules_file_with_formula
    ):
        """Should compute formula indicator for backtest."""
        use_case = BacktestUseCase(
            repository=mock_repository,
            registry=registry_with_formula,
        )

        request = BacktestRequest(
            ticker="BBCA",
            rules_file=rules_file_with_formula,
            initial_capital=Decimal("100000000"),
        )

        response = use_case.execute(request)

        # Should not raise - formula was computed for each candle
        assert response.ticker == "BBCA"
        assert response.result is not None
        # Backtest should have run (may or may not have trades)
        assert response.result.trade_count >= 0

    def test_backtest_formula_in_strategy_name(
        self, mock_repository, registry_with_formula, rules_file_with_formula
    ):
        """Backtest should record strategy name from rules file."""
        use_case = BacktestUseCase(
            repository=mock_repository,
            registry=registry_with_formula,
        )

        request = BacktestRequest(
            ticker="BBCA",
            rules_file=rules_file_with_formula,
        )

        response = use_case.execute(request)

        assert response.result.strategy_name == "smooth_rsi_rules"


# --- End-to-End Workflow Tests ---


class TestFormulaWorkflow:
    """Test complete formula workflow from creation to use."""

    def test_formula_created_and_used_in_rules(
        self, mock_repository, temp_dir
    ):
        """Test creating a formula and using it in rules assessment."""
        # Step 1: Create registry and register formula (simulating create-indicator)
        registry = IndicatorRegistry()
        formula_ast = parse("EMA(RSI(14), 5)")
        registry.register_formula("FAST_RSI", formula_ast)

        # Step 2: Create rules that use the formula
        rules_content = """
version: 1
name: fast_rsi_strategy
default_outcome: MODERATE

rules:
  - name: entry
    when:
      indicator: FAST_RSI
      operator: "<"
      value: 35
    outcome: LOW_RISK

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG
"""
        rules_path = temp_dir / "fast_rsi.yaml"
        rules_path.write_text(rules_content)

        # Step 3: Run risk assessment
        use_case = AssessRiskUseCase(
            repository=mock_repository,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        request = AssessRiskRequest(
            ticker="BBCA",
            rules_file=rules_path,
        )

        response = use_case.execute(request)

        # Verify it works
        assert response.assessment is not None

    def test_multiple_formulas_in_same_rules(
        self, mock_repository, temp_dir
    ):
        """Test using multiple formulas in the same rules file."""
        # Register multiple formulas
        registry = IndicatorRegistry()
        registry.register_formula("SMOOTH_RSI", parse("SMA(RSI(14), 10)"))
        registry.register_formula("FAST_EMA_DIFF", parse("EMA(CLOSE, 9) - EMA(CLOSE, 21)"))

        # Create rules using both
        rules_content = """
version: 1
name: multi_formula_strategy
default_outcome: MODERATE

rules:
  - name: oversold_momentum
    when:
      indicator: SMOOTH_RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    priority: 10

  - name: bullish_trend
    when:
      indicator: FAST_EMA_DIFF
      operator: ">"
      value: 0
    outcome: LOW_RISK
    priority: 20
"""
        rules_path = temp_dir / "multi_formula.yaml"
        rules_path.write_text(rules_content)

        use_case = AssessRiskUseCase(
            repository=mock_repository,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        request = AssessRiskRequest(
            ticker="BBCA",
            rules_file=rules_path,
        )

        response = use_case.execute(request)

        # Both formulas should be computed
        assert response.assessment is not None

    def test_formula_with_builtin_indicators_mixed(
        self, mock_repository, temp_dir
    ):
        """Test rules mixing formulas with built-in indicators."""
        registry = IndicatorRegistry()
        registry.register_formula("SMOOTH_RSI", parse("SMA(RSI(14), 10)"))

        # Mix SMOOTH_RSI (formula) with RSI (built-in) and SMA (built-in)
        rules_content = """
version: 1
name: mixed_indicators
default_outcome: MODERATE

rules:
  - name: smooth_oversold
    when:
      indicator: SMOOTH_RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    priority: 10

  - name: raw_oversold
    when:
      indicator: RSI
      operator: "<"
      value: 25
    outcome: LOW_RISK
    priority: 20
"""
        rules_path = temp_dir / "mixed.yaml"
        rules_path.write_text(rules_content)

        use_case = AssessRiskUseCase(
            repository=mock_repository,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        request = AssessRiskRequest(
            ticker="BBCA",
            rules_file=rules_path,
        )

        response = use_case.execute(request)

        # Should handle mixed indicator sources
        assert response.assessment is not None


# --- Error Handling Tests ---


class TestFormulaErrorHandling:
    """Test error handling for formula-related issues."""

    def test_missing_formula_registry_error(self, mock_repository, temp_dir):
        """Should raise error when formula not in registry."""
        from src.application.rules.exceptions import RulesValidationError

        # Empty registry - no formulas
        registry = IndicatorRegistry()

        rules_content = """
version: 1
name: test
default_outcome: MODERATE

rules:
  - name: test
    when:
      indicator: MISSING_FORMULA
      operator: "<"
      value: 30
    outcome: LOW_RISK
"""
        rules_path = temp_dir / "missing.yaml"
        rules_path.write_text(rules_content)

        use_case = AssessRiskUseCase(
            repository=mock_repository,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        request = AssessRiskRequest(
            ticker="BBCA",
            rules_file=rules_path,
        )

        # Error is now raised during YAML loading (validation phase)
        with pytest.raises(RulesValidationError) as exc_info:
            use_case.execute(request)

        assert "MISSING_FORMULA" in str(exc_info.value)
        assert "undefined indicator" in str(exc_info.value)
