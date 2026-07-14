"""
Tests for FormulaTranslatorAdapter and related utilities.

Verifies prompt building, response canonicalization, and mock translation.
"""

import pytest

from src.application.ports.formula_translator import (
    FormulaTranslatorError,
    TranslatorAuthError,
    TranslatorRateLimitError,
    TranslatorTimeoutError,
)
from src.infrastructure.ai.formula_translator import (
    FormulaTranslatorAdapter,
    canonicalize_formula,
)
from src.infrastructure.ai.formula_translator_prompt import (
    DEFAULT_SERIES,
    build_retry_prompt,
    build_system_prompt,
    build_user_prompt,
)


class TestBuildSystemPrompt:
    """Tests for build_system_prompt function."""

    def test_includes_all_functions(self):
        """System prompt should include all available functions."""
        prompt = build_system_prompt({"SMA", "EMA", "RSI"})

        assert "SMA" in prompt
        assert "EMA" in prompt
        assert "RSI" in prompt

    def test_functions_sorted_alphabetically(self):
        """Functions should be listed in alphabetical order."""
        prompt = build_system_prompt({"RSI", "SMA", "ATR", "EMA"})

        # Find the functions list line
        assert "ATR, EMA, RSI, SMA" in prompt

    def test_includes_default_series(self):
        """System prompt should include default series when not specified."""
        prompt = build_system_prompt({"SMA"})

        for series in DEFAULT_SERIES:
            assert series in prompt

    def test_includes_custom_series(self):
        """System prompt should include custom series when specified."""
        prompt = build_system_prompt({"SMA"}, {"CLOSE", "VOLUME", "CUSTOM"})

        assert "CLOSE" in prompt
        assert "VOLUME" in prompt
        assert "CUSTOM" in prompt

    def test_includes_operators(self):
        """System prompt should mention operators."""
        prompt = build_system_prompt({"SMA"})

        assert "+" in prompt
        assert "-" in prompt
        assert "*" in prompt
        assert "/" in prompt

    def test_includes_output_rules(self):
        """System prompt should have output rules section."""
        prompt = build_system_prompt({"SMA"})

        assert "UNSUPPORTED" in prompt
        assert "No explanations" in prompt or "no explanation" in prompt.lower()


class TestBuildUserPrompt:
    """Tests for build_user_prompt function."""

    def test_includes_intent(self):
        """User prompt should include the intent."""
        prompt = build_user_prompt("14-day RSI")

        assert "14-day RSI" in prompt
        assert "Translate to formula" in prompt

    def test_handles_empty_intent(self):
        """Should handle empty intent gracefully."""
        prompt = build_user_prompt("")

        assert "Translate to formula:" in prompt


class TestBuildRetryPrompt:
    """Tests for build_retry_prompt function."""

    def test_includes_intent_and_hint(self):
        """Retry prompt should include intent and retry hint."""
        prompt = build_retry_prompt("smoothed RSI")

        assert "smoothed RSI" in prompt
        assert "UNSUPPORTED" in prompt
        assert "Try again" in prompt


class TestCanonicalizeFormula:
    """Tests for canonicalize_formula function."""

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        result = canonicalize_formula("  SMA(CLOSE, 20)  ")

        assert result == "SMA(CLOSE, 20)"

    def test_removes_markdown_code_blocks(self):
        """Should remove markdown code block wrappers."""
        result = canonicalize_formula("```\nSMA(CLOSE, 20)\n```")

        assert result == "SMA(CLOSE, 20)"

    def test_removes_markdown_with_language(self):
        """Should remove markdown with language specifier."""
        result = canonicalize_formula("```python\nSMA(CLOSE, 20)\n```")

        assert result == "SMA(CLOSE, 20)"

    def test_takes_first_line_only(self):
        """Should take only the first non-empty line."""
        result = canonicalize_formula(
            "SMA(CLOSE, 20)\nThis is an explanation\nMore text"
        )

        assert result == "SMA(CLOSE, 20)"

    def test_uppercases_function_names(self):
        """Should uppercase function names."""
        result = canonicalize_formula("sma(rsi(14), 10)")

        assert result == "SMA(RSI(14), 10)"

    def test_uppercases_series_names(self):
        """Should uppercase series names."""
        result = canonicalize_formula("SMA(close, 20)")

        assert result == "SMA(CLOSE, 20)"

    def test_normalizes_operator_spacing(self):
        """Should normalize spacing around operators."""
        result = canonicalize_formula("EMA(CLOSE,12)-EMA(CLOSE,26)")

        # Canonicalization normalizes spacing around operators, not commas
        assert result == "EMA(CLOSE,12) - EMA(CLOSE,26)"

    def test_unsupported_prefix_returns_unsupported(self):
        """Should return UNSUPPORTED for responses starting with it."""
        result = canonicalize_formula("UNSUPPORTED - cannot translate this")

        assert result == "UNSUPPORTED"

    def test_unsupported_case_insensitive(self):
        """Should handle unsupported in any case."""
        result = canonicalize_formula("unsupported: not possible")

        assert result == "UNSUPPORTED"

    def test_empty_returns_unsupported(self):
        """Should return UNSUPPORTED for empty input."""
        result = canonicalize_formula("")

        assert result == "UNSUPPORTED"

    def test_whitespace_only_returns_unsupported(self):
        """Should return UNSUPPORTED for whitespace-only input."""
        result = canonicalize_formula("   \n\t  ")

        assert result == "UNSUPPORTED"

    def test_nested_functions(self):
        """Should handle nested function calls."""
        result = canonicalize_formula("sma(ema(rsi(14), 5), 10)")

        assert result == "SMA(EMA(RSI(14), 5), 10)"

    def test_arithmetic_operations(self):
        """Should handle arithmetic operations."""
        result = canonicalize_formula("ema(close,12)+ema(close,26)")

        # Canonicalization normalizes spacing around operators, not commas
        assert result == "EMA(CLOSE,12) + EMA(CLOSE,26)"


class TestFormulaTranslatorAdapter:
    """Tests for FormulaTranslatorAdapter."""

    def test_mock_provider_name(self):
        """Mock provider should have correct name."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        assert adapter.provider_name == "mock"

    def test_mock_translates_rsi(self):
        """Mock should translate RSI intent."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="14-day RSI",
            available_functions={"RSI", "SMA", "EMA"},
        )

        assert result == "RSI(14)"

    def test_mock_translates_smoothed_rsi(self):
        """Mock should translate smoothed RSI intent."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="smoothed RSI with 14 period and 10 day smoothing",
            available_functions={"RSI", "SMA", "EMA"},
        )

        assert result == "SMA(RSI(14), 10)"

    def test_mock_translates_macd(self):
        """Mock should translate MACD intent."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="MACD line",
            available_functions={"EMA", "SMA"},
        )

        assert result == "EMA(CLOSE, 12) - EMA(CLOSE, 26)"

    def test_mock_translates_sma(self):
        """Mock should translate SMA intent."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="20-day simple moving average",
            available_functions={"SMA", "EMA"},
        )

        assert result == "SMA(CLOSE, 20)"

    def test_mock_returns_unsupported_for_predictions(self):
        """Mock should return UNSUPPORTED for prediction requests."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="predict tomorrow's price",
            available_functions={"SMA", "EMA", "RSI"},
        )

        assert result == "UNSUPPORTED"

    def test_mock_returns_unsupported_for_buy_signals(self):
        """Mock should return UNSUPPORTED for trading signal requests."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="buy signal when RSI crosses 30",
            available_functions={"RSI", "SMA"},
        )

        assert result == "UNSUPPORTED"

    def test_mock_returns_unsupported_for_unknown_intent(self):
        """Mock should return UNSUPPORTED for unrecognized intents."""
        adapter = FormulaTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="something completely unknown",
            available_functions={"SMA", "EMA"},
        )

        assert result == "UNSUPPORTED"

    def test_invalid_provider_raises_error(self):
        """Should raise ValueError for unsupported provider."""
        with pytest.raises(ValueError) as exc:
            FormulaTranslatorAdapter(provider="invalid_provider")

        assert "Unsupported provider" in str(exc.value)

    def test_claude_without_key_raises_auth_error(self):
        """Should raise auth error when Claude API key is missing."""
        import os

        # Ensure no API key is set
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(TranslatorAuthError) as exc:
                FormulaTranslatorAdapter(provider="claude")

            assert "ANTHROPIC_API_KEY" in str(exc.value)
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_openai_without_key_raises_auth_error(self):
        """Should raise auth error when OpenAI API key is missing."""
        import os

        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(TranslatorAuthError) as exc:
                FormulaTranslatorAdapter(provider="openai")

            assert "OPENAI_API_KEY" in str(exc.value)
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_translator_errors_are_formula_translator_errors(self):
        """All specific errors should inherit from base error."""
        assert issubclass(TranslatorTimeoutError, FormulaTranslatorError)
        assert issubclass(TranslatorAuthError, FormulaTranslatorError)
        assert issubclass(TranslatorRateLimitError, FormulaTranslatorError)

    def test_errors_can_be_caught_as_base(self):
        """Should be able to catch specific errors as base type."""
        try:
            raise TranslatorTimeoutError("timeout")
        except FormulaTranslatorError as e:
            assert str(e) == "timeout"

    def test_errors_have_message(self):
        """Errors should preserve their messages."""
        error = TranslatorAuthError("Missing API key")
        assert str(error) == "Missing API key"


class TestNewModuleImports:
    """Tests for import compatibility with new split modules."""

    def test_canonicalize_formula_from_output_module(self):
        """canonicalize_formula should be importable from formula_translator_output."""
        from src.infrastructure.ai.formula_translator_output import canonicalize_formula as cf

        result = cf("sma(close, 20)")
        assert result == "SMA(CLOSE, 20)"

    def test_canonicalize_formula_from_orchestration_module(self):
        """canonicalize_formula should be re-exported from formula_translator (compat)."""
        from src.infrastructure.ai.formula_translator import canonicalize_formula as cf

        result = cf("sma(close, 20)")
        assert result == "SMA(CLOSE, 20)"

    def test_both_imports_return_same_function(self):
        """Both import paths should return the same function object."""
        from src.infrastructure.ai.formula_translator import canonicalize_formula as cf1
        from src.infrastructure.ai.formula_translator_output import canonicalize_formula as cf2

        assert cf1 is cf2

    def test_function_name_pattern_from_output_module(self):
        """FUNCTION_NAME_PATTERN should be importable from formula_translator_output."""
        from src.infrastructure.ai.formula_translator_output import FUNCTION_NAME_PATTERN

        assert FUNCTION_NAME_PATTERN.match("SMA(") is not None

    def test_all_exports_exist(self):
        """__all__ should list expected exports."""
        from src.infrastructure.ai.formula_translator import __all__

        assert "SUPPORTED_PROVIDERS" in __all__
        assert "DEFAULT_PROVIDER" in __all__
        assert "FormulaTranslatorAdapter" in __all__
        assert "canonicalize_formula" in __all__


class TestCallMockFormulaTranslator:
    """Focused tests for call_mock_formula_translator."""

    def test_smoothed_rsi(self):
        """Smoothed RSI should map to SMA(RSI(14), 10)."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: smoothed RSI")
        assert result == "SMA(RSI(14), 10)"

    def test_macd(self):
        """MACD should map to EMA(CLOSE, 12) - EMA(CLOSE, 26)."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: MACD line")
        assert result == "EMA(CLOSE, 12) - EMA(CLOSE, 26)"

    def test_rsi(self):
        """RSI should map to RSI(14)."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: 14-day RSI")
        assert result == "RSI(14)"

    def test_sma(self):
        """SMA should map to SMA(CLOSE, 20)."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator(
            "Translate to formula: 20-day simple moving average"
        )
        assert result == "SMA(CLOSE, 20)"

    def test_ema(self):
        """EMA should map to EMA(CLOSE, 20)."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator(
            "Translate to formula: exponential moving average"
        )
        assert result == "EMA(CLOSE, 20)"

    def test_atr(self):
        """ATR should map to ATR(14)."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: true range 14")
        assert result == "ATR(14)"

    def test_unsupported_predict(self):
        """Predict intent should return UNSUPPORTED."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: predict price")
        assert result == "UNSUPPORTED"

    def test_unsupported_buy_signal(self):
        """Buy/sell signal intent should return UNSUPPORTED."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator(
            "Translate to formula: buy signal when RSI crosses 30"
        )
        assert result == "UNSUPPORTED"

    def test_unsupported_advice(self):
        """Advice intent should return UNSUPPORTED."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: give me advice")
        assert result == "UNSUPPORTED"

    def test_unsupported_recommend(self):
        """Recommend intent should return UNSUPPORTED."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator("Translate to formula: recommend something")
        assert result == "UNSUPPORTED"

    def test_unsupported_fallback(self):
        """Unknown intent should return UNSUPPORTED."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            call_mock_formula_translator,
        )

        result = call_mock_formula_translator(
            "Translate to formula: something completely unknown"
        )
        assert result == "UNSUPPORTED"

    def test_unsupported_keywords_list(self):
        """UNSUPPORTED_KEYWORDS should contain expected keywords."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            UNSUPPORTED_KEYWORDS,
        )

        assert "predict" in UNSUPPORTED_KEYWORDS
        assert "buy" in UNSUPPORTED_KEYWORDS
        assert "sell" in UNSUPPORTED_KEYWORDS
        assert "signal" in UNSUPPORTED_KEYWORDS
        assert "advice" in UNSUPPORTED_KEYWORDS
        assert "recommend" in UNSUPPORTED_KEYWORDS

    def test_unsupported_keywords_not_empty(self):
        """UNSUPPORTED_KEYWORDS should not be empty."""
        from src.infrastructure.ai.formula_translator_mock_templates import (
            UNSUPPORTED_KEYWORDS,
        )

        assert len(UNSUPPORTED_KEYWORDS) > 0


class TestRetryBehavior:
    """Tests for retry-once-when-UNSUPPORTED behavior."""

    def test_retries_when_first_output_is_unsupported(self, monkeypatch):
        """Should retry once when first call returns UNSUPPORTED."""
        call_log: list[int] = []

        def patched_call_llm(_self, system_prompt: str, user_prompt: str) -> str:
            call_log.append(len(call_log) + 1)
            if len(call_log) == 1:
                return "UNSUPPORTED"
            return "RSI(14)"

        monkeypatch.setattr(
            "src.infrastructure.ai.formula_translator.FormulaTranslatorAdapter._call_llm",
            patched_call_llm,
        )

        adapter = FormulaTranslatorAdapter(provider="mock")
        result = adapter.translate(
            intent="14-day RSI",
            available_functions={"RSI", "SMA", "EMA"},
        )

        assert result == "RSI(14)"
        assert len(call_log) == 2, (
            f"Expected exactly 2 calls to _call_llm, got {len(call_log)}"
        )

    def test_no_retry_when_first_output_is_valid(self, monkeypatch):
        """Should NOT retry when first call returns a valid formula."""
        call_log: list[int] = []

        def patched_call_llm(_self, system_prompt: str, user_prompt: str) -> str:
            call_log.append(len(call_log) + 1)
            return "RSI(14)"

        monkeypatch.setattr(
            "src.infrastructure.ai.formula_translator.FormulaTranslatorAdapter._call_llm",
            patched_call_llm,
        )

        adapter = FormulaTranslatorAdapter(provider="mock")
        result = adapter.translate(
            intent="14-day RSI",
            available_functions={"RSI", "SMA", "EMA"},
        )

        assert result == "RSI(14)"
        assert len(call_log) == 1, (
            f"Expected exactly 1 call to _call_llm, got {len(call_log)}"
        )
