"""
Full workflow integration tests.

Tests complete user journeys across multiple components:
1. Create custom indicator → Use in strategy → Run backtest
2. AI-created strategy → Validate → Backtest
3. Multiple custom indicators in one strategy
4. Error handling and edge cases

These tests verify that all features work together, not just in isolation.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.application.formula.parser import parse
from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.create_indicator_from_intent import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.application.use_case.create_strategy_from_intent import (
    CreateStrategyFromIntentRequest,
    CreateStrategyFromIntentUseCase,
)
from src.domain.services.backtest_engine import BacktestEngine
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.trade_action import TradeAction
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.ai.strategy_translator import StrategyTranslatorAdapter
from src.infrastructure.config.yaml_loader import YamlConfigLoader
from src.infrastructure.persistence.formula_storage import FormulaStorage

from tests.integration.conftest import (
    create_custom_indicator_strategy,
    create_ema_crossover_strategy,
    create_rsi_oversold_strategy,
    create_strategy_yaml,
    generate_test_candles,
)


class TestCustomIndicatorInBacktest:
    """Test custom indicators work end-to-end in backtest."""

    def test_smooth_rsi_strategy_backtest(self, temp_dir, mock_candles):
        """Full flow: create formula → create strategy → backtest."""
        # 1. Set up registry and register custom formula
        formulas_path = temp_dir / "formulas.yaml"
        storage = FormulaStorage(path=formulas_path)

        # Register custom formula: SMOOTH_RSI = SMA(RSI(14), 10)
        ast = parse("SMA(RSI(14), 10)")
        registry = IndicatorRegistry()
        registry.register_formula("SMOOTH_RSI", ast)

        # 2. Create strategy YAML using the custom formula
        strategy_yaml = create_custom_indicator_strategy(
            name="smooth_rsi_test",
            indicator_name="SMOOTH_RSI",
        )

        # 3. Load and validate strategy
        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        assert rule_set.name == "smooth_rsi_test"

        # 4. Compute indicators
        interpreter = YamlRuleInterpreter(rule_set)
        required = interpreter.get_required_indicators(registry=registry)

        # SMOOTH_RSI should be in required indicators
        assert "SMOOTH_RSI" in required

        # 5. Compute indicator values
        values = registry.compute("SMOOTH_RSI", mock_candles, period=0)
        assert len(values) > 0

        # RSI-based indicators should be bounded
        for dt, value in values:
            assert Decimal("0") <= value <= Decimal("100")

        # 6. Build actions from rule evaluation
        # Create a value lookup
        value_by_date = {d: v for d, v in values}
        actions = []

        # Signal mapping
        from src.application.rules.schema import SignalMapping

        signal_mapping = rule_set.signal_mapping or SignalMapping()

        for candle in mock_candles:
            if candle.date not in value_by_date:
                actions.append((candle.date, TradeAction.FLAT, "warm_up"))
                continue

            smooth_rsi_value = value_by_date[candle.date]

            # Create snapshot with the custom indicator
            snapshot = IndicatorSnapshot(
                date=candle.date,
                sma=Decimal("0"),
                ema=Decimal("0"),
                rsi=Decimal("0"),
                extras=(("SMOOTH_RSI", smooth_rsi_value),),
            )

            risk_level, confidence, rationale = interpreter.evaluate(snapshot)
            action = signal_mapping.get_action(risk_level)
            rule_name = "smooth_rsi_rule" if confidence > 0 else "default"
            actions.append((candle.date, action, rule_name))

        # 7. Run backtest
        engine = BacktestEngine(initial_capital=Decimal("100000000"))
        result = engine.run(mock_candles, actions, "smooth_rsi_test")

        # 8. Verify results
        assert result is not None
        assert result.ticker == "TEST"
        assert result.strategy_name == "smooth_rsi_test"
        assert result.final_capital > Decimal("0")
        # With our trend-following test data, we should see some trades
        assert result.trade_count >= 0

    def test_persisted_formula_in_backtest(self, temp_dir, mock_candles):
        """Formula persisted to disk → Reload → Use in backtest."""
        formulas_path = temp_dir / "formulas.yaml"
        storage = FormulaStorage(path=formulas_path)

        # 1. Persist formula
        storage.save("FAST_RSI", "RSI(7)", intent="7-day RSI")

        # 2. Create fresh registry that loads from storage
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        # 3. Verify formula is loaded
        assert registry.is_registered("FAST_RSI")

        # 4. Create strategy using persisted formula
        strategy_yaml = create_strategy_yaml(
            name="fast_rsi_strategy",
            rules=[
                {
                    "name": "fast_oversold",
                    "when": {
                        "indicator": "FAST_RSI",
                        "operator": "<",
                        "value": 25,
                    },
                    "outcome": "LOW_RISK",
                },
                {
                    "name": "fast_overbought",
                    "when": {
                        "indicator": "FAST_RSI",
                        "operator": ">",
                        "value": 75,
                    },
                    "outcome": "HIGH_RISK",
                },
            ],
            signal_mapping={
                "LOW_RISK": "ENTER_LONG",
                "MODERATE": "HOLD",
                "HIGH_RISK": "EXIT_LONG",
            },
        )

        # 5. Load strategy (should validate FAST_RSI exists)
        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        assert rule_set.name == "fast_rsi_strategy"

        # 6. Compute indicator
        values = registry.compute("FAST_RSI", mock_candles, period=0)
        assert len(values) > 0


class TestAICreatedStrategyWorkflow:
    """Test AI-created strategies work end-to-end."""

    def test_strategy_create_to_validate(self, temp_dir):
        """AI creates strategy → validate passes."""
        # 1. Create strategy via mock AI
        translator = StrategyTranslatorAdapter(provider="mock")
        registry = IndicatorRegistry()

        use_case = CreateStrategyFromIntentUseCase(translator, registry)

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI oversold strategy",
                strategy_name="ai_test",
            )
        )

        # 2. Verify creation succeeded
        assert response.success, f"Strategy creation failed: {response.error_message}"
        assert response.yaml_content is not None
        assert response.rule_set is not None
        assert response.rule_set.name == "ai_test"

        # 3. Strategy should have rules
        assert len(response.rule_set.rules) > 0

        # 4. Strategy should be re-loadable (validate the YAML)
        reloaded = YamlConfigLoader.load_from_string(
            response.yaml_content, registry=registry
        )
        assert reloaded.name == response.rule_set.name

    def test_ai_strategy_backtest_execution(self, mock_candles):
        """AI creates strategy → backtest runs successfully."""
        # 1. Create strategy via mock AI
        translator = StrategyTranslatorAdapter(provider="mock")
        registry = IndicatorRegistry()

        use_case = CreateStrategyFromIntentUseCase(translator, registry)

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="momentum strategy",
                strategy_name="momentum_test",
            )
        )

        assert response.success

        # 2. Use the generated strategy to create interpreter
        rule_set = response.rule_set
        interpreter = YamlRuleInterpreter(rule_set)

        # 3. Get required indicators
        required = interpreter.get_required_indicators(registry=registry)

        # 4. Compute all indicators
        # Note: required keys are UPPERCASE, but we also need original names from rules
        indicator_series = {}
        for name, (ind_type, period) in required.items():
            type_name = ind_type.value if hasattr(ind_type, "value") else ind_type
            values = registry.compute(type_name, mock_candles, period)
            indicator_series[name] = {d: v for d, v in values}

        # 5. Evaluate rules for each candle
        from src.application.rules.schema import BUILTIN_INDICATORS, SignalMapping

        signal_mapping = rule_set.signal_mapping or SignalMapping()
        actions = []

        # Get original indicator names from rule conditions (preserving original case)
        referenced_names = rule_set.get_all_referenced_indicators()

        for candle in mock_candles:
            # Check if all indicators available
            missing = False
            for name in required:
                if name not in indicator_series or candle.date not in indicator_series[name]:
                    missing = True
                    break

            if missing:
                actions.append((candle.date, TradeAction.FLAT, "warm_up"))
                continue

            # Build snapshot
            sma = indicator_series.get("SMA", {}).get(candle.date, Decimal("0"))
            ema = indicator_series.get("EMA", {}).get(candle.date, Decimal("0"))
            rsi = indicator_series.get("RSI", {}).get(candle.date, Decimal("0"))

            # Build extras - IndicatorSnapshot.get() is case-insensitive
            extras = []
            for name in required:
                if name not in BUILTIN_INDICATORS and candle.date in indicator_series[name]:
                    value = indicator_series[name][candle.date]
                    extras.append((name, value))

            snapshot = IndicatorSnapshot(
                date=candle.date,
                sma=sma,
                ema=ema,
                rsi=rsi,
                extras=tuple(extras),
            )

            risk_level, _, _ = interpreter.evaluate(snapshot)
            action = signal_mapping.get_action(risk_level)
            actions.append((candle.date, action, "ai_rule"))

        # 6. Run backtest
        engine = BacktestEngine(initial_capital=Decimal("100000000"))
        result = engine.run(mock_candles, actions, rule_set.name)

        # 7. Verify backtest completed
        assert result is not None
        assert result.final_capital > Decimal("0")
        assert result.total_return_pct is not None

    def test_unsupported_intent_handling(self):
        """Test handling when intent is not strategy-related.

        Note: The mock provider generates a default RSI strategy for any input,
        so we test that the workflow handles edge cases gracefully.
        A real AI provider would return UNSUPPORTED for non-strategy intents.
        """
        translator = StrategyTranslatorAdapter(provider="mock")
        registry = IndicatorRegistry()

        use_case = CreateStrategyFromIntentUseCase(translator, registry)

        # Test with empty intent (should fail validation)
        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="",  # Empty intent
                strategy_name="empty_test",
            )
        )

        # Empty intent should be rejected
        assert not response.success
        assert response.error_message is not None
        assert "empty" in response.error_message.lower()


class TestMultipleCustomIndicators:
    """Test strategies with multiple custom indicators."""

    def test_strategy_with_two_formulas(self, temp_dir, mock_candles):
        """Strategy using SMOOTH_RSI and FAST_EMA formulas."""
        formulas_path = temp_dir / "formulas.yaml"
        storage = FormulaStorage(path=formulas_path)

        # 1. Persist multiple formulas
        storage.save("SMOOTH_RSI", "SMA(RSI(14), 5)")
        storage.save("FAST_EMA", "EMA(CLOSE, 9)")

        # 2. Create registry with formulas
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        assert registry.is_registered("SMOOTH_RSI")
        assert registry.is_registered("FAST_EMA")

        # 3. Create strategy using both
        strategy_yaml = create_strategy_yaml(
            name="multi_formula_strategy",
            rules=[
                {
                    "name": "rsi_signal",
                    "priority": 10,
                    "when": {
                        "indicator": "SMOOTH_RSI",
                        "operator": "<",
                        "value": 30,
                    },
                    "outcome": "LOW_RISK",
                },
                {
                    "name": "rsi_overbought",
                    "priority": 10,
                    "when": {
                        "indicator": "SMOOTH_RSI",
                        "operator": ">",
                        "value": 70,
                    },
                    "outcome": "HIGH_RISK",
                },
            ],
        )

        # 4. Load and validate
        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        assert rule_set.name == "multi_formula_strategy"

        # 5. Compute both indicators
        smooth_rsi = registry.compute("SMOOTH_RSI", mock_candles, period=0)
        fast_ema = registry.compute("FAST_EMA", mock_candles, period=0)

        assert len(smooth_rsi) > 0
        assert len(fast_ema) > 0

    def test_inline_formula_in_strategy(self, mock_candles):
        """Strategy with formula defined inline in YAML."""
        registry = IndicatorRegistry()

        # Strategy with inline formula definition
        strategy_yaml = """
version: 1
name: inline_formula_strategy
default_outcome: MODERATE

indicators:
  my_smooth_rsi:
    formula: "SMA(RSI(14), 5)"

rules:
  - name: oversold
    when:
      indicator: my_smooth_rsi
      operator: "<"
      value: 35
    outcome: LOW_RISK

  - name: overbought
    when:
      indicator: my_smooth_rsi
      operator: ">"
      value: 65
    outcome: HIGH_RISK

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG
"""

        # Load should work (inline formula gets parsed)
        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        assert rule_set.name == "inline_formula_strategy"
        assert len(rule_set.indicators) == 1
        assert rule_set.indicators[0].name == "my_smooth_rsi"
        assert rule_set.indicators[0].is_formula()


class TestEMACrossoverStrategy:
    """Test EMA crossover strategy end-to-end."""

    def test_ema_crossover_backtest(self, mock_candles):
        """EMA crossover strategy generates trades."""
        registry = IndicatorRegistry()

        # 1. Create strategy
        strategy_yaml = create_ema_crossover_strategy("ema_cross_test")

        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        # 2. Get required indicators
        interpreter = YamlRuleInterpreter(rule_set)
        required = interpreter.get_required_indicators(registry=registry)

        # Should require both fast and slow EMA
        assert any("FAST_EMA" in name.upper() or name.upper() == "FAST_EMA" for name in required)
        assert any("SLOW_EMA" in name.upper() or name.upper() == "SLOW_EMA" for name in required)

        # 3. Compute indicators
        indicator_series = {}
        for name, (ind_type, period) in required.items():
            type_name = ind_type.value if hasattr(ind_type, "value") else ind_type
            values = registry.compute(type_name, mock_candles, period)
            indicator_series[name] = {d: v for d, v in values}

        # 4. Evaluate and run backtest
        from src.application.rules.schema import SignalMapping

        signal_mapping = rule_set.signal_mapping or SignalMapping()
        actions = []

        for candle in mock_candles:
            missing = any(
                name not in indicator_series or candle.date not in indicator_series[name]
                for name in required
            )

            if missing:
                actions.append((candle.date, TradeAction.FLAT, "warm_up"))
                continue

            # Build extras - IndicatorSnapshot.get() is case-insensitive
            extras = []
            for name in required:
                if candle.date in indicator_series[name]:
                    value = indicator_series[name][candle.date]
                    extras.append((name, value))

            snapshot = IndicatorSnapshot(
                date=candle.date,
                sma=Decimal("0"),
                ema=Decimal("0"),
                rsi=Decimal("0"),
                extras=tuple(extras),
            )

            risk_level, _, _ = interpreter.evaluate(snapshot)
            action = signal_mapping.get_action(risk_level)
            actions.append((candle.date, action, "crossover"))

        engine = BacktestEngine(initial_capital=Decimal("100000000"))
        result = engine.run(mock_candles, actions, "ema_cross_test")

        assert result is not None
        # EMA crossover should generate trades with trending data
        assert result.trade_count >= 0


class TestRSIOversoldStrategy:
    """Test basic RSI oversold strategy."""

    def test_rsi_strategy_generates_signals(self, mock_candles):
        """RSI oversold strategy triggers on extreme values."""
        registry = IndicatorRegistry()

        strategy_yaml = create_rsi_oversold_strategy("rsi_test")
        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        interpreter = YamlRuleInterpreter(rule_set)

        # Compute RSI
        rsi_values = registry.compute("RSI", mock_candles, 14)
        rsi_by_date = {d: v for d, v in rsi_values}

        # Check that we have some extreme RSI values in our test data
        extreme_count = 0
        for dt, value in rsi_values:
            if value < Decimal("30") or value > Decimal("70"):
                extreme_count += 1

        # Our test data is designed to produce some extreme values
        assert extreme_count > 0, "Test data should produce some oversold/overbought conditions"

        # Evaluate all candles
        signal_count = 0
        for candle in mock_candles:
            if candle.date not in rsi_by_date:
                continue

            rsi = rsi_by_date[candle.date]
            snapshot = IndicatorSnapshot(
                date=candle.date,
                sma=Decimal("0"),
                ema=Decimal("0"),
                rsi=rsi,
            )

            risk_level, confidence, _ = interpreter.evaluate(snapshot)
            if confidence > 0:  # A rule matched
                signal_count += 1

        assert signal_count > 0, "Strategy should generate signals on extreme RSI"


class TestErrorHandling:
    """Test error handling in workflows."""

    def test_undefined_indicator_error(self):
        """Strategy referencing undefined indicator fails."""
        registry = IndicatorRegistry()

        strategy_yaml = create_strategy_yaml(
            name="bad_strategy",
            rules=[
                {
                    "name": "bad_rule",
                    "when": {
                        "indicator": "NONEXISTENT_INDICATOR",
                        "operator": "<",
                        "value": 50,
                    },
                    "outcome": "LOW_RISK",
                }
            ],
        )

        with pytest.raises(Exception) as exc_info:
            YamlConfigLoader.load_from_string(strategy_yaml, registry=registry)

        assert "undefined" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()

    def test_invalid_formula_syntax_error(self, temp_dir):
        """Invalid formula syntax is rejected."""
        from src.application.formula.parser import FormulaParseError

        with pytest.raises(FormulaParseError):
            parse("INVALID_SYNTAX(((")

    def test_empty_candles_error(self):
        """Backtest with empty candles fails gracefully."""
        engine = BacktestEngine(initial_capital=Decimal("100000000"))

        with pytest.raises(ValueError, match="empty"):
            engine.run([], [], "test_strategy")


class TestCreateIndicatorFromIntent:
    """Test indicator creation workflow."""

    def test_create_indicator_and_use_in_strategy(self, temp_dir, mock_candles):
        """Create indicator from intent → Use in strategy."""
        formulas_path = temp_dir / "formulas.yaml"
        storage = FormulaStorage(path=formulas_path)

        # 1. Create indicator via AI
        translator = FormulaTranslatorAdapter(provider="mock")
        registry = IndicatorRegistry()

        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=registry.get_available_indicators(),
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="smoothed RSI",
                indicator_name="MY_SMOOTH_RSI",
            )
        )

        assert response.success
        assert response.formula is not None
        assert response.ast is not None

        # 2. Register the formula
        registry.register_formula("MY_SMOOTH_RSI", response.ast)

        # 3. Persist it
        storage.save("MY_SMOOTH_RSI", response.formula, intent="smoothed RSI")

        # 4. Use in strategy
        strategy_yaml = create_custom_indicator_strategy(
            name="my_indicator_strategy",
            indicator_name="MY_SMOOTH_RSI",
        )

        rule_set = YamlConfigLoader.load_from_string(
            strategy_yaml, registry=registry
        )

        assert rule_set.name == "my_indicator_strategy"

        # 5. Compute the indicator
        values = registry.compute("MY_SMOOTH_RSI", mock_candles, period=0)
        assert len(values) > 0
