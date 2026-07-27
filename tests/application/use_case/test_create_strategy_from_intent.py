"""
Tests for CreateStrategyFromIntentUseCase.

Verifies the use case orchestrates AI translation correctly and
handles all error cases gracefully.
"""

import pytest

from src.application.ports.strategy_translator import (
    StrategyTranslatorAuthError,
    StrategyTranslatorError,
    StrategyTranslatorRateLimitError,
    StrategyTranslatorTimeoutError,
)
from src.application.rules.schema import RuleSet
from src.application.use_case.create_strategy_from_intent_use_case import (
    CreateStrategyFromIntentRequest,
    CreateStrategyFromIntentResponse,
    CreateStrategyFromIntentUseCase,
)
from src.infrastructure.ai.strategy_translator import StrategyTranslatorAdapter
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


class MockStrategyTranslator:
    """Mock translator for testing."""

    def __init__(self, return_value: str = "UNSUPPORTED"):
        self.return_value = return_value
        self.provider_name = "mock"
        self.call_count = 0
        self.last_intent: str | None = None
        self.last_strategy_name: str | None = None
        self.last_available_indicators: set[str] | None = None

    def translate(
        self,
        intent: str,
        strategy_name: str,
        available_indicators: set[str],
    ) -> str:
        self.call_count += 1
        self.last_intent = intent
        self.last_strategy_name = strategy_name
        self.last_available_indicators = available_indicators
        return self.return_value


class FailingStrategyTranslator:
    """Translator that raises specific errors."""

    def __init__(self, error_class: type, message: str = "Test error"):
        self._error_class = error_class
        self._message = message
        self.provider_name = "failing"

    def translate(
        self,
        intent: str,
        strategy_name: str,
        available_indicators: set[str],
    ) -> str:
        raise self._error_class(self._message)


# Valid YAML for testing
VALID_RSI_YAML = """version: 1
name: "test_rsi"
description: "RSI strategy"

default_outcome: MODERATE

rules:
  - name: rsi_oversold
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30"
"""

VALID_EMA_YAML = """version: 1
name: "test_ema"
description: "EMA crossover strategy"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

rules:
  - name: bullish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
"""


class TestCreateStrategyFromIntentUseCase:
    """Tests for CreateStrategyFromIntentUseCase."""

    @pytest.fixture
    def registry(self):
        """Create indicator registry for tests."""
        return create_indicator_registry()

    def test_successful_translation_simple_rsi(self, registry):
        """Should successfully translate simple RSI strategy."""
        translator = MockStrategyTranslator(return_value=VALID_RSI_YAML)
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI oversold strategy",
                strategy_name="test_rsi",
            )
        )

        assert response.success is True
        assert response.unsupported is False
        assert response.yaml_content == VALID_RSI_YAML
        assert response.rule_set is not None
        assert isinstance(response.rule_set, RuleSet)
        assert response.strategy_name == "test_rsi"
        assert response.error_message is None
        assert response.provider == "mock"

    def test_successful_translation_ema_crossover(self, registry):
        """Should successfully translate EMA crossover strategy."""
        translator = MockStrategyTranslator(return_value=VALID_EMA_YAML)
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="EMA crossover with 9 and 21 periods",
                strategy_name="test_ema",
            )
        )

        assert response.success is True
        assert response.rule_set is not None
        assert len(response.rule_set.indicators) == 2
        assert len(response.rule_set.rules) == 1

    def test_unsupported_intent_returns_unsupported_response(self, registry):
        """Should return unsupported response for unsupported intents."""
        translator = MockStrategyTranslator(return_value="UNSUPPORTED")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="predict tomorrow's price",
                strategy_name="prediction",
            )
        )

        assert response.success is False
        assert response.unsupported is True
        assert response.yaml_content is None
        assert response.rule_set is None
        assert response.error_message is None  # UNSUPPORTED is not an error

    def test_empty_intent_returns_error(self, registry):
        """Should return error for empty intent."""
        translator = MockStrategyTranslator()
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert response.unsupported is False
        assert "empty" in response.error_message.lower()
        assert translator.call_count == 0  # Should not call translator

    def test_empty_strategy_name_returns_error(self, registry):
        """Should return error for empty strategy name."""
        translator = MockStrategyTranslator()
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI strategy",
                strategy_name="",
            )
        )

        assert response.success is False
        assert "name" in response.error_message.lower()
        assert translator.call_count == 0

    def test_whitespace_only_intent_returns_error(self, registry):
        """Should return error for whitespace-only intent."""
        translator = MockStrategyTranslator()
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="   \t\n  ",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert "empty" in response.error_message.lower()

    def test_invalid_yaml_syntax_returns_error(self, registry):
        """Should return error when LLM returns invalid YAML."""
        invalid_yaml = "version: 1\nname: test\n  invalid: indentation"
        translator = MockStrategyTranslator(return_value=invalid_yaml)
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="broken yaml",
                strategy_name="broken",
            )
        )

        assert response.success is False
        assert response.unsupported is False
        assert response.error_message is not None

    def test_invalid_schema_returns_error(self, registry):
        """Should return error when YAML has invalid schema."""
        # Missing required field 'rules'
        invalid_schema = """version: 1
name: "invalid"
default_outcome: MODERATE
"""
        translator = MockStrategyTranslator(return_value=invalid_schema)
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="invalid schema",
                strategy_name="invalid",
            )
        )

        assert response.success is False
        assert (
            "schema" in response.error_message.lower() or "rules" in response.error_message.lower()
        )

    def test_undefined_indicator_returns_error(self, registry):
        """Should return error when YAML references undefined indicator."""
        yaml_with_undefined = """version: 1
name: "undefined"
default_outcome: MODERATE

rules:
  - name: bad_rule
    when:
      indicator: UNDEFINED_INDICATOR
      operator: "<"
      value: 30
    outcome: LOW_RISK
"""
        translator = MockStrategyTranslator(return_value=yaml_with_undefined)
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="undefined indicator",
                strategy_name="undefined",
            )
        )

        assert response.success is False
        assert (
            "undefined" in response.error_message.lower()
            or "invalid" in response.error_message.lower()
        )

    def test_handles_auth_error(self, registry):
        """Should return error response for auth failures."""
        translator = FailingStrategyTranslator(StrategyTranslatorAuthError, "No API key")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI strategy",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert response.unsupported is False
        assert "No API key" in response.error_message

    def test_handles_timeout_error(self, registry):
        """Should return error response for timeouts."""
        translator = FailingStrategyTranslator(StrategyTranslatorTimeoutError, "Request timed out")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI strategy",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert "timed out" in response.error_message.lower()

    def test_handles_rate_limit_error(self, registry):
        """Should return error response for rate limits."""
        translator = FailingStrategyTranslator(
            StrategyTranslatorRateLimitError, "Rate limit exceeded"
        )
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI strategy",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert "Rate limit" in response.error_message

    def test_handles_generic_translator_error(self, registry):
        """Should return error response for generic translator errors."""
        translator = FailingStrategyTranslator(StrategyTranslatorError, "API error")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI strategy",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert "API error" in response.error_message

    def test_handles_unexpected_error(self, registry):
        """Should handle unexpected exceptions gracefully."""
        translator = FailingStrategyTranslator(RuntimeError, "Unexpected failure")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI strategy",
                strategy_name="test",
            )
        )

        assert response.success is False
        assert "Unexpected" in response.error_message

    def test_passes_available_indicators_to_translator(self, registry):
        """Should pass available indicators to translator."""
        translator = MockStrategyTranslator(return_value="UNSUPPORTED")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="test",
                strategy_name="test",
            )
        )

        # Should include built-in indicators
        assert "RSI" in translator.last_available_indicators
        assert "SMA" in translator.last_available_indicators
        assert "EMA" in translator.last_available_indicators

    def test_strips_intent_before_translation(self, registry):
        """Should strip whitespace from intent before translation."""
        translator = MockStrategyTranslator(return_value="UNSUPPORTED")
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="  RSI strategy  ",
                strategy_name="test",
            )
        )

        assert translator.last_intent == "RSI strategy"


class TestResponseFactoryMethods:
    """Tests for CreateStrategyFromIntentResponse factory methods."""

    @pytest.fixture
    def registry(self):
        """Create indicator registry for tests."""
        return create_indicator_registry()

    def test_success_response(self, registry):
        """Test success_response factory method."""
        from src.infrastructure.config.yaml_loader import YamlConfigLoader

        rule_set = YamlConfigLoader.load_from_string(VALID_RSI_YAML, registry=registry)
        response = CreateStrategyFromIntentResponse.success_response(
            intent="RSI strategy",
            yaml_content=VALID_RSI_YAML,
            rule_set=rule_set,
            strategy_name="test_rsi",
            provider="test",
        )

        assert response.success is True
        assert response.unsupported is False
        assert response.yaml_content == VALID_RSI_YAML
        assert response.rule_set is rule_set
        assert response.strategy_name == "test_rsi"
        assert response.error_message is None
        assert response.provider == "test"

    def test_unsupported_response(self):
        """Test unsupported_response factory method."""
        response = CreateStrategyFromIntentResponse.unsupported_response(
            intent="predict price",
            strategy_name="prediction",
            provider="test",
        )

        assert response.success is False
        assert response.unsupported is True
        assert response.yaml_content is None
        assert response.rule_set is None
        assert response.strategy_name == "prediction"
        assert response.error_message is None
        assert response.provider == "test"

    def test_error_response(self):
        """Test error_response factory method."""
        response = CreateStrategyFromIntentResponse.error_response(
            intent="bad intent",
            strategy_name="bad",
            error_message="Something went wrong",
            provider="test",
        )

        assert response.success is False
        assert response.unsupported is False
        assert response.yaml_content is None
        assert response.rule_set is None
        assert response.error_message == "Something went wrong"
        assert response.provider == "test"


class TestWithRealMockAdapter:
    """Integration tests using StrategyTranslatorAdapter with mock provider."""

    @pytest.fixture
    def registry(self):
        """Create indicator registry for tests."""
        return create_indicator_registry()

    def test_end_to_end_rsi_translation(self, registry):
        """End-to-end test with real mock adapter."""
        adapter = StrategyTranslatorAdapter(provider="mock")
        use_case = CreateStrategyFromIntentUseCase(
            translator=adapter,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="RSI oversold strategy",
                strategy_name="rsi_test",
            )
        )

        assert response.success is True
        assert response.rule_set is not None
        assert "RSI" in response.yaml_content

    def test_end_to_end_ema_crossover(self, registry):
        """End-to-end test for EMA crossover."""
        adapter = StrategyTranslatorAdapter(provider="mock")
        use_case = CreateStrategyFromIntentUseCase(
            translator=adapter,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="EMA crossover strategy",
                strategy_name="ema_test",
            )
        )

        assert response.success is True
        assert response.rule_set is not None
        assert "EMA" in response.yaml_content

    def test_end_to_end_unsupported(self, registry):
        """End-to-end test for unsupported intent."""
        adapter = StrategyTranslatorAdapter(provider="mock")
        use_case = CreateStrategyFromIntentUseCase(
            translator=adapter,
            registry=registry,
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent="predict BBCA price",
                strategy_name="prediction",
            )
        )

        assert response.success is False
        assert response.unsupported is True
