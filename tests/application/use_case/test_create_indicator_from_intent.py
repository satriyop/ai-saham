"""
Tests for CreateIndicatorFromIntentUseCase.

Verifies the use case orchestrates AI translation correctly and
handles all error cases gracefully.
"""


from src.application.formula.ast_nodes import FunctionCallNode
from src.application.ports.formula_translator import (
    FormulaTranslatorError,
    TranslatorAuthError,
    TranslatorRateLimitError,
    TranslatorTimeoutError,
)
from src.application.use_case.create_indicator_from_intent_use_case import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentResponse,
    CreateIndicatorFromIntentUseCase,
)
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter


class MockTranslator:
    """Mock translator for testing."""

    def __init__(self, return_value: str = "RSI(14)"):
        self.return_value = return_value
        self.provider_name = "mock"
        self.call_count = 0
        self.last_intent: str | None = None
        self.last_available_functions: set[str] | None = None

    def translate(
        self,
        intent: str,
        available_functions: set[str],
        available_series: set[str] | None = None,
    ) -> str:
        self.call_count += 1
        self.last_intent = intent
        self.last_available_functions = available_functions
        return self.return_value


class FailingTranslator:
    """Translator that raises specific errors."""

    def __init__(self, error_class: type, message: str = "Test error"):
        self._error_class = error_class
        self._message = message
        self.provider_name = "failing"

    def translate(
        self,
        intent: str,
        available_functions: set[str],
        available_series: set[str] | None = None,
    ) -> str:
        raise self._error_class(self._message)


class TestCreateIndicatorFromIntentUseCase:
    """Tests for CreateIndicatorFromIntentUseCase."""

    def test_successful_translation_simple_rsi(self):
        """Should successfully translate simple RSI intent."""
        translator = MockTranslator(return_value="RSI(14)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI", "SMA", "EMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is True
        assert response.unsupported is False
        assert response.formula == "RSI(14)"
        assert response.ast is not None
        assert isinstance(response.ast, FunctionCallNode)
        assert response.ast.name == "RSI"
        assert response.error_message is None
        assert response.provider == "mock"

    def test_successful_translation_smoothed_rsi(self):
        """Should successfully translate nested formula."""
        translator = MockTranslator(return_value="SMA(RSI(14), 10)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI", "SMA", "EMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="smoothed RSI with 14 period and 10 day smoothing"
            )
        )

        assert response.success is True
        assert response.formula == "SMA(RSI(14), 10)"
        assert isinstance(response.ast, FunctionCallNode)
        assert response.ast.name == "SMA"

    def test_successful_translation_macd_line(self):
        """Should successfully translate arithmetic formula."""
        translator = MockTranslator(return_value="EMA(CLOSE, 12) - EMA(CLOSE, 26)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"EMA", "SMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="difference between 12 and 26 day EMA"
            )
        )

        assert response.success is True
        assert response.formula == "EMA(CLOSE, 12) - EMA(CLOSE, 26)"

    def test_preserves_indicator_name(self):
        """Should preserve indicator name in response."""
        translator = MockTranslator(return_value="RSI(14)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="14-day RSI",
                indicator_name="MY_RSI",
            )
        )

        assert response.success is True
        assert response.indicator_name == "MY_RSI"

    def test_unsupported_intent_returns_unsupported_response(self):
        """Should return unsupported response for unsupported intents."""
        translator = MockTranslator(return_value="UNSUPPORTED")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI", "SMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="predict tomorrow's price")
        )

        assert response.success is False
        assert response.unsupported is True
        assert response.formula is None
        assert response.ast is None
        assert response.error_message is None  # UNSUPPORTED is not an error

    def test_empty_intent_returns_error(self):
        """Should return error for empty intent."""
        translator = MockTranslator()
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="")
        )

        assert response.success is False
        assert response.unsupported is False
        assert "empty" in response.error_message.lower()
        assert translator.call_count == 0  # Should not call translator

    def test_whitespace_only_intent_returns_error(self):
        """Should return error for whitespace-only intent."""
        translator = MockTranslator()
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="   \t\n  ")
        )

        assert response.success is False
        assert "empty" in response.error_message.lower()

    def test_invalid_syntax_returns_error(self):
        """Should return error when LLM returns invalid formula syntax."""
        translator = MockTranslator(return_value="SMA(CLOSE, )")  # Invalid syntax
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"SMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="broken formula")
        )

        assert response.success is False
        assert response.unsupported is False
        assert "syntax" in response.error_message.lower()

    def test_unknown_indicator_returns_error(self):
        """Should return error when LLM uses unknown indicator."""
        translator = MockTranslator(return_value="UNKNOWN(14)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI", "SMA"},  # UNKNOWN not available
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="some intent")
        )

        assert response.success is False
        assert response.unsupported is False
        assert "validation" in response.error_message.lower() or "Unknown" in response.error_message

    def test_handles_auth_error(self):
        """Should return error response for auth failures."""
        translator = FailingTranslator(TranslatorAuthError, "No API key")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is False
        assert response.unsupported is False
        assert "No API key" in response.error_message

    def test_handles_timeout_error(self):
        """Should return error response for timeouts."""
        translator = FailingTranslator(TranslatorTimeoutError, "Request timed out")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is False
        assert "timed out" in response.error_message.lower()

    def test_handles_rate_limit_error(self):
        """Should return error response for rate limits."""
        translator = FailingTranslator(TranslatorRateLimitError, "Rate limit exceeded")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is False
        assert "Rate limit" in response.error_message

    def test_handles_generic_translator_error(self):
        """Should return error response for generic translator errors."""
        translator = FailingTranslator(FormulaTranslatorError, "API error")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is False
        assert "API error" in response.error_message

    def test_handles_unexpected_error(self):
        """Should handle unexpected exceptions gracefully."""
        translator = FailingTranslator(RuntimeError, "Unexpected failure")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is False
        assert "Unexpected" in response.error_message

    def test_passes_available_functions_to_translator(self):
        """Should pass available functions to translator."""
        translator = MockTranslator()
        functions = {"RSI", "SMA", "EMA", "ATR"}
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=functions,
        )

        use_case.execute(CreateIndicatorFromIntentRequest(intent="test"))

        assert translator.last_available_functions == functions

    def test_strips_intent_before_translation(self):
        """Should strip whitespace from intent before translation."""
        translator = MockTranslator()
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        use_case.execute(
            CreateIndicatorFromIntentRequest(intent="  14-day RSI  ")
        )

        assert translator.last_intent == "14-day RSI"


class TestResponseFactoryMethods:
    """Tests for CreateIndicatorFromIntentResponse factory methods."""

    def test_success_response(self):
        """Test success_response factory method."""
        from src.application.formula.parser import parse

        ast = parse("RSI(14)")
        response = CreateIndicatorFromIntentResponse.success_response(
            intent="14-day RSI",
            formula="RSI(14)",
            ast=ast,
            indicator_name="MY_RSI",
            provider="test",
        )

        assert response.success is True
        assert response.unsupported is False
        assert response.formula == "RSI(14)"
        assert response.ast is ast
        assert response.indicator_name == "MY_RSI"
        assert response.error_message is None
        assert response.provider == "test"

    def test_unsupported_response(self):
        """Test unsupported_response factory method."""
        response = CreateIndicatorFromIntentResponse.unsupported_response(
            intent="predict price",
            provider="test",
        )

        assert response.success is False
        assert response.unsupported is True
        assert response.formula is None
        assert response.ast is None
        assert response.indicator_name is None
        assert response.error_message is None
        assert response.provider == "test"

    def test_error_response(self):
        """Test error_response factory method."""
        response = CreateIndicatorFromIntentResponse.error_response(
            intent="bad intent",
            error_message="Something went wrong",
            provider="test",
        )

        assert response.success is False
        assert response.unsupported is False
        assert response.formula is None
        assert response.ast is None
        assert response.error_message == "Something went wrong"
        assert response.provider == "test"


class TestWithRealMockAdapter:
    """Integration tests using FormulaTranslatorAdapter with mock provider."""

    def test_end_to_end_rsi_translation(self):
        """End-to-end test with real mock adapter."""
        adapter = FormulaTranslatorAdapter(provider="mock")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=adapter,
            available_functions={"RSI", "SMA", "EMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="14-day RSI")
        )

        assert response.success is True
        assert response.formula == "RSI(14)"

    def test_end_to_end_smoothed_rsi(self):
        """End-to-end test for smoothed RSI."""
        adapter = FormulaTranslatorAdapter(provider="mock")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=adapter,
            available_functions={"RSI", "SMA", "EMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="smoothed RSI with 14 period"
            )
        )

        assert response.success is True
        assert response.formula == "SMA(RSI(14), 10)"

    def test_end_to_end_unsupported(self):
        """End-to-end test for unsupported intent."""
        adapter = FormulaTranslatorAdapter(provider="mock")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=adapter,
            available_functions={"RSI", "SMA", "EMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="buy signal when RSI crosses 30")
        )

        assert response.success is False
        assert response.unsupported is True


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_formula_with_series_only(self):
        """Should handle formulas that are just series references."""
        translator = MockTranslator(return_value="CLOSE")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"SMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="closing price")
        )

        # CLOSE is a series, not a function, so it should parse successfully
        assert response.success is True
        assert response.formula == "CLOSE"

    def test_formula_with_number_only(self):
        """Should handle formulas that are just numbers."""
        translator = MockTranslator(return_value="14")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"SMA"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="the number 14")
        )

        # Pure numbers should parse successfully
        assert response.success is True

    def test_long_intent_string(self):
        """Should handle very long intent strings."""
        translator = MockTranslator(return_value="RSI(14)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        long_intent = "Calculate the " + ("very " * 100) + "long RSI"
        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent=long_intent)
        )

        # Should not fail for long intents
        assert response.success is True

    def test_special_characters_in_intent(self):
        """Should handle special characters in intent."""
        translator = MockTranslator(return_value="RSI(14)")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"RSI"},
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(intent="RSI(14) with 'quotes' & symbols!")
        )

        assert response.success is True
