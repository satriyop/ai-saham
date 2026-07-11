"""
Tests for StrategyTranslatorAdapter and related utilities.

Verifies prompt building, response canonicalization, and mock translation.
"""

import pytest

from src.application.ports.strategy_translator import (
    StrategyTranslatorAuthError,
    StrategyTranslatorError,
    StrategyTranslatorRateLimitError,
    StrategyTranslatorTimeoutError,
)
from src.infrastructure.ai.strategy_translator import (
    StrategyTranslatorAdapter,
    canonicalize_yaml,
)
from src.infrastructure.ai.strategy_translator_mock_templates import (
    call_mock_strategy_translator,
)
from src.infrastructure.ai.strategy_translator_output import (
    canonicalize_yaml as output_canonicalize_yaml,
)
from src.infrastructure.ai.strategy_translator_prompt import (
    build_retry_prompt,
    build_system_prompt,
    build_user_prompt,
)


class TestBuildSystemPrompt:
    """Tests for build_system_prompt function."""

    def test_includes_all_indicators(self):
        """System prompt should include all available indicators."""
        prompt = build_system_prompt({"SMA", "EMA", "RSI", "ATR"})

        assert "SMA" in prompt
        assert "EMA" in prompt
        assert "RSI" in prompt
        assert "ATR" in prompt

    def test_indicators_sorted_alphabetically(self):
        """Indicators should be listed in alphabetical order."""
        prompt = build_system_prompt({"RSI", "SMA", "ATR", "EMA"})

        # Find the indicators list line
        assert "ATR, EMA, RSI, SMA" in prompt

    def test_includes_yaml_schema(self):
        """System prompt should include YAML schema."""
        prompt = build_system_prompt({"SMA"})

        assert "version: 1" in prompt
        assert "default_outcome" in prompt
        assert "rules:" in prompt
        assert "indicators:" in prompt

    def test_includes_operators(self):
        """System prompt should mention operators."""
        prompt = build_system_prompt({"SMA"})

        assert "<" in prompt
        assert ">" in prompt
        assert "==" in prompt
        assert "!=" in prompt

    def test_includes_outcomes(self):
        """System prompt should include outcome options."""
        prompt = build_system_prompt({"SMA"})

        assert "LOW_RISK" in prompt
        assert "MODERATE" in prompt
        assert "HIGH_RISK" in prompt

    def test_includes_signal_mapping(self):
        """System prompt should explain signal mapping."""
        prompt = build_system_prompt({"SMA"})

        assert "ENTER_LONG" in prompt
        assert "EXIT_LONG" in prompt
        assert "HOLD" in prompt

    def test_includes_examples(self):
        """System prompt should have examples."""
        prompt = build_system_prompt({"SMA"})

        assert "Example" in prompt
        assert "rsi_oversold" in prompt or "RSI" in prompt

    def test_includes_unsupported_guidance(self):
        """System prompt should explain UNSUPPORTED responses."""
        prompt = build_system_prompt({"SMA"})

        assert "UNSUPPORTED" in prompt


class TestBuildUserPrompt:
    """Tests for build_user_prompt function."""

    def test_includes_intent_and_name(self):
        """User prompt should include intent and strategy name."""
        prompt = build_user_prompt("RSI strategy", "my_rsi")

        assert "RSI strategy" in prompt
        assert "my_rsi" in prompt

    def test_handles_empty_intent(self):
        """Should handle empty intent gracefully."""
        prompt = build_user_prompt("", "test")

        assert "Strategy name: test" in prompt


class TestBuildRetryPrompt:
    """Tests for build_retry_prompt function."""

    def test_includes_intent_and_hint(self):
        """Retry prompt should include intent and retry hint."""
        prompt = build_retry_prompt("RSI strategy", "retry_test")

        assert "RSI strategy" in prompt
        assert "retry_test" in prompt
        assert "UNSUPPORTED" in prompt
        assert "Try again" in prompt


class TestCanonicalizeYaml:
    """Tests for canonicalize_yaml function."""

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        result = canonicalize_yaml("  version: 1\nname: test  ")

        assert result == "version: 1\nname: test"

    def test_removes_markdown_code_blocks(self):
        """Should remove markdown code block wrappers."""
        result = canonicalize_yaml("```\nversion: 1\nname: test\n```")

        assert result == "version: 1\nname: test"

    def test_removes_markdown_with_yaml_language(self):
        """Should remove markdown with yaml language specifier."""
        result = canonicalize_yaml("```yaml\nversion: 1\nname: test\n```")

        assert result == "version: 1\nname: test"

    def test_removes_markdown_with_yml_language(self):
        """Should remove markdown with yml language specifier."""
        result = canonicalize_yaml("```yml\nversion: 1\nname: test\n```")

        assert result == "version: 1\nname: test"

    def test_preserves_multiline_yaml(self):
        """Should preserve all lines in YAML content."""
        yaml_content = """version: 1
name: test
rules:
  - name: rule1
"""
        result = canonicalize_yaml(yaml_content)

        assert "version: 1" in result
        assert "name: test" in result
        assert "rules:" in result
        assert "rule1" in result

    def test_unsupported_prefix_returns_unsupported(self):
        """Should return UNSUPPORTED for responses starting with it."""
        result = canonicalize_yaml("UNSUPPORTED - cannot translate this")

        assert result == "UNSUPPORTED"

    def test_unsupported_case_insensitive(self):
        """Should handle unsupported in any case."""
        result = canonicalize_yaml("unsupported: not possible")

        assert result == "UNSUPPORTED"

    def test_empty_returns_unsupported(self):
        """Should return UNSUPPORTED for empty input."""
        result = canonicalize_yaml("")

        assert result == "UNSUPPORTED"

    def test_whitespace_only_returns_unsupported(self):
        """Should return UNSUPPORTED for whitespace-only input."""
        result = canonicalize_yaml("   \n\t  ")

        assert result == "UNSUPPORTED"


class TestStrategyTranslatorAdapter:
    """Tests for StrategyTranslatorAdapter."""

    def test_mock_provider_name(self):
        """Mock provider should have correct name."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        assert adapter.provider_name == "mock"

    def test_mock_translates_rsi_strategy(self):
        """Mock should translate RSI strategy intent."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="RSI oversold strategy",
            strategy_name="rsi_test",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert "version: 1" in result
        assert "rsi_test" in result
        assert "RSI" in result
        assert "LOW_RISK" in result

    def test_mock_translates_ema_crossover(self):
        """Mock should translate EMA crossover intent."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="EMA crossover strategy",
            strategy_name="ema_test",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert "version: 1" in result
        assert "fast_ema" in result
        assert "slow_ema" in result
        assert "EMA" in result

    def test_mock_translates_rsi_ema_combined(self):
        """Mock should translate combined RSI and EMA strategy."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="RSI with EMA crossover confirmation",
            strategy_name="combined_test",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert "version: 1" in result
        # Should have both RSI and EMA rules
        assert "RSI" in result
        assert "EMA" in result

    def test_mock_translates_conservative_strategy(self):
        """Mock should translate conservative strategy."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="conservative RSI strategy",
            strategy_name="conservative_test",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert "version: 1" in result
        assert "conservative" in result.lower()

    def test_mock_translates_momentum_strategy(self):
        """Mock should translate momentum strategy."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="momentum strategy",
            strategy_name="momentum_test",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert "version: 1" in result
        assert "momentum" in result.lower()

    def test_mock_returns_unsupported_for_predictions(self):
        """Mock should return UNSUPPORTED for prediction requests."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="predict tomorrow's price",
            strategy_name="prediction",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert result == "UNSUPPORTED"

    def test_mock_returns_unsupported_for_specific_stocks(self):
        """Mock should return UNSUPPORTED for specific stock requests."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="strategy for BBCA stock",
            strategy_name="bbca",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert result == "UNSUPPORTED"

    def test_mock_returns_unsupported_for_guaranteed_outcomes(self):
        """Mock should return UNSUPPORTED for guaranteed outcome requests."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="strategy that always wins",
            strategy_name="winner",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert result == "UNSUPPORTED"

    def test_mock_returns_unsupported_for_explanations(self):
        """Mock should return UNSUPPORTED for explanation requests."""
        adapter = StrategyTranslatorAdapter(provider="mock")

        result = adapter.translate(
            intent="explain what RSI is",
            strategy_name="explain",
            available_indicators={"RSI", "SMA", "EMA"},
        )

        assert result == "UNSUPPORTED"

    def test_invalid_provider_raises_error(self):
        """Should raise ValueError for unsupported provider."""
        with pytest.raises(ValueError) as exc:
            StrategyTranslatorAdapter(provider="invalid_provider")

        assert "Unsupported provider" in str(exc.value)

    def test_claude_without_key_raises_auth_error(self):
        """Should raise auth error when Claude API key is missing."""
        import os

        # Ensure no API key is set
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(StrategyTranslatorAuthError) as exc:
                StrategyTranslatorAdapter(provider="claude")

            assert "ANTHROPIC_API_KEY" in str(exc.value)
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_openai_without_key_raises_auth_error(self):
        """Should raise auth error when OpenAI API key is missing."""
        import os

        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(StrategyTranslatorAuthError) as exc:
                StrategyTranslatorAdapter(provider="openai")

            assert "OPENAI_API_KEY" in str(exc.value)
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original

    def test_gemini_without_key_raises_auth_error(self):
        """Should raise auth error when Gemini API key is missing."""
        import os

        original = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            with pytest.raises(StrategyTranslatorAuthError) as exc:
                StrategyTranslatorAdapter(provider="gemini")

            assert "GOOGLE_API_KEY" in str(exc.value)
        finally:
            if original:
                os.environ["GOOGLE_API_KEY"] = original

    def test_ollama_provider_name_with_model(self):
        """Ollama provider should include model in name."""
        adapter = StrategyTranslatorAdapter(provider="ollama", model="llama3")

        assert adapter.provider_name == "ollama:llama3"


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_translator_errors_are_strategy_translator_errors(self):
        """All specific errors should inherit from base error."""
        assert issubclass(StrategyTranslatorTimeoutError, StrategyTranslatorError)
        assert issubclass(StrategyTranslatorAuthError, StrategyTranslatorError)
        assert issubclass(StrategyTranslatorRateLimitError, StrategyTranslatorError)

    def test_errors_can_be_caught_as_base(self):
        """Should be able to catch specific errors as base type."""
        try:
            raise StrategyTranslatorTimeoutError("timeout")
        except StrategyTranslatorError as e:
            assert str(e) == "timeout"

    def test_errors_have_message(self):
        """Errors should preserve their messages."""
        error = StrategyTranslatorAuthError("Missing API key")
        assert str(error) == "Missing API key"


class TestMockYamlValidation:
    """Tests to verify mock responses generate valid YAML."""

    def test_mock_rsi_yaml_is_valid(self):
        """Mock RSI YAML should be parseable."""
        import yaml

        adapter = StrategyTranslatorAdapter(provider="mock")
        result = adapter.translate(
            intent="RSI strategy",
            strategy_name="valid_test",
            available_indicators={"RSI"},
        )

        # Should not raise
        parsed = yaml.safe_load(result)
        assert parsed["version"] == 1
        assert parsed["name"] == "valid_test"
        assert "rules" in parsed

    def test_mock_ema_yaml_is_valid(self):
        """Mock EMA YAML should be parseable."""
        import yaml

        adapter = StrategyTranslatorAdapter(provider="mock")
        result = adapter.translate(
            intent="EMA crossover",
            strategy_name="ema_valid",
            available_indicators={"EMA"},
        )

        # Should not raise
        parsed = yaml.safe_load(result)
        assert parsed["version"] == 1
        assert "indicators" in parsed
        assert "rules" in parsed

    def test_mock_yaml_has_required_fields(self):
        """Mock YAML should have all required fields."""
        import yaml

        adapter = StrategyTranslatorAdapter(provider="mock")
        result = adapter.translate(
            intent="RSI strategy",
            strategy_name="complete_test",
            available_indicators={"RSI"},
        )

        parsed = yaml.safe_load(result)

        # Required fields
        assert "version" in parsed
        assert "name" in parsed
        assert "default_outcome" in parsed
        assert "rules" in parsed
        assert len(parsed["rules"]) > 0

        # Each rule should have required fields
        for rule in parsed["rules"]:
            assert "name" in rule
            assert "when" in rule
            assert "outcome" in rule


class TestOutputCanonicalizeYaml:
    """Direct import coverage for strategy_translator_output.canonicalize_yaml."""

    def test_matches_facade_reexport(self):
        """Facade re-export should be the same function object."""
        assert canonicalize_yaml is output_canonicalize_yaml

    def test_strips_markdown_fence(self):
        """Should strip a fenced yaml code block."""
        result = output_canonicalize_yaml("```yaml\nversion: 1\n```")

        assert result == "version: 1"


class TestCallMockStrategyTranslator:
    """Direct import coverage for strategy_translator_mock_templates."""

    def test_matches_adapter_for_rsi(self):
        adapter = StrategyTranslatorAdapter(provider="mock")
        intent, strategy_name = "RSI oversold strategy", "rsi_test"
        expected = adapter.translate(
            intent=intent,
            strategy_name=strategy_name,
            available_indicators={"RSI", "SMA", "EMA"},
        )

        user_prompt = build_user_prompt(intent, strategy_name)
        result = canonicalize_yaml(call_mock_strategy_translator(user_prompt))

        assert result == expected

    def test_matches_adapter_for_ema_crossover(self):
        adapter = StrategyTranslatorAdapter(provider="mock")
        intent, strategy_name = "EMA crossover strategy", "ema_test"
        expected = adapter.translate(
            intent=intent,
            strategy_name=strategy_name,
            available_indicators={"RSI", "SMA", "EMA"},
        )

        user_prompt = build_user_prompt(intent, strategy_name)
        result = canonicalize_yaml(call_mock_strategy_translator(user_prompt))

        assert result == expected

    def test_matches_adapter_for_rsi_ema_combined(self):
        adapter = StrategyTranslatorAdapter(provider="mock")
        intent, strategy_name = "RSI with EMA crossover confirmation", "combined_test"
        expected = adapter.translate(
            intent=intent,
            strategy_name=strategy_name,
            available_indicators={"RSI", "SMA", "EMA"},
        )

        user_prompt = build_user_prompt(intent, strategy_name)
        result = canonicalize_yaml(call_mock_strategy_translator(user_prompt))

        assert result == expected

    def test_matches_adapter_for_unsupported_prediction(self):
        adapter = StrategyTranslatorAdapter(provider="mock")
        intent, strategy_name = "predict tomorrow's price", "prediction"
        expected = adapter.translate(
            intent=intent,
            strategy_name=strategy_name,
            available_indicators={"RSI", "SMA", "EMA"},
        )

        user_prompt = build_user_prompt(intent, strategy_name)
        result = call_mock_strategy_translator(user_prompt)

        assert result == expected
        assert result == "UNSUPPORTED"
