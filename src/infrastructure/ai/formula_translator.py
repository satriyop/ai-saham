"""
Formula translator adapter with multi-provider support.

Implements the FormulaTranslator port using various LLM providers
(Claude, OpenAI, Gemini, Ollama, or mock for testing).

Layer: Infrastructure
"""

import logging
import os
import re
import time

from src.application.ports.formula_translator import (
    FormulaTranslatorError,
    TranslatorAuthError,
    TranslatorRateLimitError,
    TranslatorTimeoutError,
)
from src.infrastructure.ai.formula_translator_prompt import (
    DEFAULT_SERIES,
    FORMULA_TRANSLATOR_MAX_RETRIES,
    FORMULA_TRANSLATOR_MAX_TOKENS,
    FORMULA_TRANSLATOR_TIMEOUT_SECONDS,
    build_retry_prompt,
    build_system_prompt,
    build_user_prompt,
)

from src.infrastructure.config.app_config import APP_CFG

logger = logging.getLogger("ai_saham.ai.translator")

# Supported providers
SUPPORTED_PROVIDERS = ("claude", "openai", "gemini", "ollama", "mock")
DEFAULT_PROVIDER: str = APP_CFG.ai.provider

# Pattern for function names in formulas
FUNCTION_NAME_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def canonicalize_formula(raw: str) -> str:
    """Normalize formula output from LLM.

    - Strip leading/trailing whitespace
    - Remove markdown code blocks
    - Take first line only (ignore explanations)
    - Uppercase function names (SMA, EMA, RSI)
    - Normalize spacing around operators
    - Handle common LLM quirks

    Args:
        raw: Raw LLM output string.

    Returns:
        Canonicalized formula string or "UNSUPPORTED".

    Example:
        >>> canonicalize_formula("```\nsma(rsi(14), 10)\n```")
        'SMA(RSI(14), 10)'
        >>> canonicalize_formula("UNSUPPORTED - cannot translate")
        'UNSUPPORTED'
    """
    # Strip whitespace
    result = raw.strip()

    # Remove markdown code blocks
    result = re.sub(r"^```[a-z]*\n?", "", result)
    result = re.sub(r"\n?```$", "", result)
    result = result.strip()

    # Take first non-empty line only
    lines = result.split("\n")
    result = ""
    for line in lines:
        line = line.strip()
        if line:
            result = line
            break

    if not result:
        return "UNSUPPORTED"

    # Check for UNSUPPORTED (case-insensitive, with any suffix)
    if result.upper().startswith("UNSUPPORTED"):
        return "UNSUPPORTED"

    # Uppercase function names
    def uppercase_function(match: re.Match) -> str:
        return match.group(1).upper() + "("

    result = FUNCTION_NAME_PATTERN.sub(uppercase_function, result)

    # Uppercase series names
    for series in DEFAULT_SERIES:
        # Word boundary replacement for series names
        pattern = re.compile(rf"\b{series}\b", re.IGNORECASE)
        result = pattern.sub(series, result)

    # Normalize spacing around operators
    result = re.sub(r"\s*([+\-*/])\s*", r" \1 ", result)

    # Clean up multiple spaces
    result = re.sub(r"\s+", " ", result)
    result = result.strip()

    return result


class FormulaTranslatorAdapter:
    """Single adapter supporting all providers for formula translation.

    This adapter handles the common translation logic (prompt building,
    retry with hint, canonicalization) and delegates API calls to
    provider-specific methods.

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
        if provider is None:
            provider = os.getenv("AI_PROVIDER", DEFAULT_PROVIDER).lower()
        else:
            provider = provider.lower()

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
        if self._provider == "claude":
            return self._call_claude(system_prompt, user_prompt)
        elif self._provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        elif self._provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        elif self._provider == "ollama":
            return self._call_ollama(system_prompt, user_prompt)
        else:  # mock
            return self._call_mock(system_prompt, user_prompt)

    def _call_claude(self, system_prompt: str, user_prompt: str) -> str:
        """Call Claude API."""
        try:
            import anthropic
        except ImportError:
            raise FormulaTranslatorError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        try:
            client = anthropic.Anthropic(
                api_key=self._api_key,
                timeout=FORMULA_TRANSLATOR_TIMEOUT_SECONDS,
                max_retries=FORMULA_TRANSLATOR_MAX_RETRIES,
            )

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=FORMULA_TRANSLATOR_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            return message.content[0].text if message.content else ""

        except anthropic.AuthenticationError as e:
            raise TranslatorAuthError(f"Invalid API key for claude: {e}")
        except anthropic.RateLimitError as e:
            raise TranslatorRateLimitError(f"Rate limit exceeded: {e}")
        except anthropic.APITimeoutError as e:
            raise TranslatorTimeoutError(f"Request timed out: {e}")
        except anthropic.APIError as e:
            raise FormulaTranslatorError(f"Claude API error: {e}")

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise FormulaTranslatorError(
                "openai package not installed. Run: pip install openai"
            )

        try:
            client = openai.OpenAI(
                api_key=self._api_key,
                timeout=FORMULA_TRANSLATOR_TIMEOUT_SECONDS,
                max_retries=FORMULA_TRANSLATOR_MAX_RETRIES,
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=FORMULA_TRANSLATOR_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            return response.choices[0].message.content or ""

        except openai.AuthenticationError as e:
            raise TranslatorAuthError(f"Invalid API key for openai: {e}")
        except openai.RateLimitError as e:
            raise TranslatorRateLimitError(f"Rate limit exceeded: {e}")
        except openai.APITimeoutError as e:
            raise TranslatorTimeoutError(f"Request timed out: {e}")
        except openai.APIError as e:
            raise FormulaTranslatorError(f"OpenAI API error: {e}")

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Call Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise FormulaTranslatorError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        try:
            genai.configure(api_key=self._api_key)

            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=system_prompt,
            )

            response = model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=FORMULA_TRANSLATOR_MAX_TOKENS,
                ),
            )

            return response.text if response.text else ""

        except Exception as e:
            error_str = str(e).lower()
            if "invalid api key" in error_str or "api key" in error_str:
                raise TranslatorAuthError(f"Invalid API key for gemini: {e}")
            if "rate limit" in error_str or "quota" in error_str:
                raise TranslatorRateLimitError(f"Rate limit exceeded: {e}")
            if "timeout" in error_str:
                raise TranslatorTimeoutError(f"Request timed out: {e}")
            raise FormulaTranslatorError(f"Gemini API error: {e}")

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Call Ollama API via HTTP."""
        import json
        import urllib.request
        from urllib.error import URLError

        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        model = self._model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

        url = f"{host.rstrip('/')}/api/chat"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": FORMULA_TRANSLATOR_MAX_TOKENS,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, timeout=FORMULA_TRANSLATOR_TIMEOUT_SECONDS
            ) as response:
                result = json.loads(response.read().decode("utf-8"))

            return result.get("message", {}).get("content", "")

        except TimeoutError:
            raise TranslatorTimeoutError(
                f"Ollama request timed out after {FORMULA_TRANSLATOR_TIMEOUT_SECONDS}s"
            )
        except URLError as e:
            if "timed out" in str(e).lower():
                raise TranslatorTimeoutError(f"Ollama request timed out: {e}")
            raise FormulaTranslatorError(
                f"Failed to connect to Ollama at {host}: {e}. "
                "Is Ollama running? Start with: ollama serve"
            )
        except json.JSONDecodeError as e:
            raise FormulaTranslatorError(f"Invalid response from Ollama: {e}")
        except Exception as e:
            raise FormulaTranslatorError(f"Ollama error: {e}")

    def _call_mock(self, system_prompt: str, user_prompt: str) -> str:
        """Return mock response for testing."""
        # Extract intent from user prompt
        intent = user_prompt.replace("Translate to formula: ", "").strip()
        intent_lower = intent.lower()

        # Check for unsupported intents FIRST (before any indicator keywords)
        unsupported_keywords = ["predict", "buy", "sell", "signal", "advice", "recommend"]
        if any(kw in intent_lower for kw in unsupported_keywords):
            return "UNSUPPORTED"

        # Mock translations based on keywords
        if "rsi" in intent_lower and "smooth" in intent_lower:
            return "SMA(RSI(14), 10)"
        if "macd" in intent_lower:
            return "EMA(CLOSE, 12) - EMA(CLOSE, 26)"
        if "rsi" in intent_lower:
            return "RSI(14)"
        if "sma" in intent_lower or "simple moving" in intent_lower:
            return "SMA(CLOSE, 20)"
        if "ema" in intent_lower or "exponential" in intent_lower:
            return "EMA(CLOSE, 20)"
        if "atr" in intent_lower or "true range" in intent_lower:
            return "ATR(14)"

        return "UNSUPPORTED"
