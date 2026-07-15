"""
Formula translator adapter with multi-provider support.

Implements the FormulaTranslator port using various LLM providers
(Claude, OpenAI, Gemini, Ollama, or mock for testing).

Layer: Infrastructure
"""

# Compatibility surface:
# - Canonical import(s):
#   - canonicalize_formula -> src.infrastructure.ai.formula_translator_output
# - Allowed contents:
#   - re-export only for canonicalize_formula. This module remains canonical
#     for FormulaTranslatorAdapter itself, which is not part of the
#     compatibility surface.
# - Expiry:
#   - permanent public API, or remove after internal imports migrate to
#     src.infrastructure.ai.formula_translator_output directly.

import logging
import os
import time

from src.application.ports.formula_translator import (
    TranslatorAuthError,
)
from src.infrastructure.ai.formula_translator_clients import (
    call_formula_translator_provider,
)
from src.infrastructure.ai.formula_translator_mock_templates import (
    call_mock_formula_translator,
)
from src.infrastructure.ai.formula_translator_output import canonicalize_formula
from src.infrastructure.ai.formula_translator_prompt import (
    DEFAULT_SERIES,
    build_retry_prompt,
    build_system_prompt,
    build_user_prompt,
)
from src.infrastructure.ai.provider_config import resolve_ai_provider

logger = logging.getLogger("ai_saham.ai.translator")

# Supported providers
SUPPORTED_PROVIDERS = ("claude", "openai", "gemini", "ollama", "mock")


# Re-exported for backward compatibility with existing imports:
# from src.infrastructure.ai.formula_translator import canonicalize_formula
__all__ = [
    "SUPPORTED_PROVIDERS",
    "FormulaTranslatorAdapter",
    "canonicalize_formula",
]


class FormulaTranslatorAdapter:
    """Single adapter supporting all providers for formula translation.

    This adapter handles the common translation logic (prompt building,
    retry with hint, canonicalization) and delegates API calls to
    provider-specific clients.

    Example:
        translator = FormulaTranslatorAdapter(provider="claude")
        result = translator.translate(
            intent="smoothed RSI with 14-period",
            available_functions={"SMA", "EMA", "RSI"},
        )
        # Returns: "SMA(RSI(14), 10)" or "UNSUPPORTED"
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """Initialize the translator adapter.

        Args:
            provider: Provider name. If None, reads from AI_PROVIDER env var.
                     Supported: claude, openai, gemini, ollama, mock
            api_key: API key for the provider. If None, reads from env var.
            model: Model name override (for Ollama).

        Raises:
            TranslatorAuthError: If required API key is missing.
            ValueError: If provider is not supported.
        """
        provider = resolve_ai_provider(provider)

        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
            )

        self._provider = provider
        self._api_key = api_key
        self._model = model

        # Validate API key for providers that need it
        if provider in ("claude", "openai", "gemini"):
            self._validate_api_key()

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        if self._provider == "ollama" and self._model:
            return f"ollama:{self._model}"
        return self._provider

    def translate(
        self,
        intent: str,
        available_functions: set[str],
        available_series: set[str] | None = None,
    ) -> str:
        """Translate natural language intent into a formula string.

        Args:
            intent: Natural language description of the indicator.
            available_functions: Set of available function names (uppercase).
            available_series: Set of available series names. If None, uses defaults.

        Returns:
            Formula string OR "UNSUPPORTED".

        Raises:
            TranslatorTimeoutError: If the request times out.
            TranslatorAuthError: If authentication fails.
            TranslatorRateLimitError: If rate limit is exceeded.
            FormulaTranslatorError: For other translation errors.
        """
        if available_series is None:
            available_series = set(DEFAULT_SERIES)

        system_prompt = build_system_prompt(available_functions, available_series)
        user_prompt = build_user_prompt(intent)

        logger.info(f"Translate request: provider={self.provider_name}, intent={intent!r}")

        start_time = time.time()
        try:
            # First attempt
            raw = self._call_llm(system_prompt, user_prompt)
            result = canonicalize_formula(raw)

            # Retry once with hint if UNSUPPORTED
            if result == "UNSUPPORTED":
                logger.debug("First attempt returned UNSUPPORTED, retrying with hint")
                retry_prompt = build_retry_prompt(intent)
                raw = self._call_llm(system_prompt, retry_prompt)
                result = canonicalize_formula(raw)

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Translate result: formula={result!r}, time={elapsed_ms}ms")
            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Translate error: {type(e).__name__}: {e}")
            raise

    def _validate_api_key(self) -> None:
        """Validate that API key is available for the provider."""
        env_vars = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }

        env_var = env_vars.get(self._provider)
        if not env_var:
            return

        key = self._api_key or os.getenv(env_var)
        if not key:
            raise TranslatorAuthError(
                f"No API key for {self._provider} (set {env_var} environment variable)"
            )
        self._api_key = key

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the appropriate LLM provider.

        Args:
            system_prompt: The system prompt.
            user_prompt: The user prompt.

        Returns:
            Raw LLM output string.
        """
        if self._provider == "mock":
            return call_mock_formula_translator(user_prompt)

        return call_formula_translator_provider(
            provider=self._provider,
            api_key=self._api_key,
            model=self._model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
