"""
Strategy translator adapter with multi-provider support.

Implements the StrategyTranslator port using various LLM providers
(Claude, OpenAI, Gemini, Ollama, or mock for testing).

Layer: Infrastructure
"""

import logging
import os
import re
import time

from src.application.ports.strategy_translator import (
    StrategyTranslatorAuthError,
    StrategyTranslatorError,
    StrategyTranslatorRateLimitError,
    StrategyTranslatorTimeoutError,
)
from src.infrastructure.ai.strategy_translator_prompt import (
    STRATEGY_TRANSLATOR_MAX_RETRIES,
    STRATEGY_TRANSLATOR_MAX_TOKENS,
    STRATEGY_TRANSLATOR_TIMEOUT_SECONDS,
    build_retry_prompt,
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger("ai_saham.ai.strategy_translator")

# Supported providers
SUPPORTED_PROVIDERS = ("claude", "openai", "gemini", "ollama", "mock")
DEFAULT_PROVIDER = "claude"


def canonicalize_yaml(raw: str) -> str:
    """Normalize YAML output from LLM.

    - Strip leading/trailing whitespace
    - Remove markdown code blocks
    - Handle common LLM quirks

    Args:
        raw: Raw LLM output string.

    Returns:
        Canonicalized YAML string or "UNSUPPORTED".

    Example:
        >>> canonicalize_yaml("```yaml\\nversion: 1\\n```")
        'version: 1'
        >>> canonicalize_yaml("UNSUPPORTED - cannot translate")
        'UNSUPPORTED'
    """
    # Strip whitespace
    result = raw.strip()

    # Remove markdown code blocks (yaml, yml, or plain)
    result = re.sub(r"^```(?:ya?ml)?\s*\n?", "", result)
    result = re.sub(r"\n?```\s*$", "", result)
    result = result.strip()

    if not result:
        return "UNSUPPORTED"

    # Check for UNSUPPORTED (case-insensitive, with any suffix)
    if result.upper().startswith("UNSUPPORTED"):
        return "UNSUPPORTED"

    return result


class StrategyTranslatorAdapter:
    """Single adapter supporting all providers for strategy translation.

    This adapter handles the common translation logic (prompt building,
    retry with hint, canonicalization) and delegates API calls to
    provider-specific methods.

    Example:
        translator = StrategyTranslatorAdapter(provider="claude")
        result = translator.translate(
            intent="RSI oversold strategy",
            strategy_name="rsi_oversold",
            available_indicators={"RSI", "SMA", "EMA"},
        )
        # Returns: valid YAML string or "UNSUPPORTED"
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
            StrategyTranslatorAuthError: If required API key is missing.
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
        strategy_name: str,
        available_indicators: set[str],
    ) -> str:
        """Translate natural language intent into strategy YAML.

        Args:
            intent: Natural language description of the strategy.
            strategy_name: Name for the generated strategy.
            available_indicators: Set of available indicator names (uppercase).

        Returns:
            Valid YAML string OR "UNSUPPORTED".

        Raises:
            StrategyTranslatorTimeoutError: If the request times out.
            StrategyTranslatorAuthError: If authentication fails.
            StrategyTranslatorRateLimitError: If rate limit is exceeded.
            StrategyTranslatorError: For other translation errors.
        """
        system_prompt = build_system_prompt(available_indicators)
        user_prompt = build_user_prompt(intent, strategy_name)

        logger.info(
            f"Translate request: provider={self.provider_name}, "
            f"intent={intent!r}, strategy={strategy_name!r}"
        )

        start_time = time.time()
        try:
            # First attempt
            raw = self._call_llm(system_prompt, user_prompt)
            result = canonicalize_yaml(raw)

            # Retry once with hint if UNSUPPORTED
            if result == "UNSUPPORTED":
                logger.debug("First attempt returned UNSUPPORTED, retrying with hint")
                retry_prompt = build_retry_prompt(intent, strategy_name)
                raw = self._call_llm(system_prompt, retry_prompt)
                result = canonicalize_yaml(raw)

            elapsed_ms = int((time.time() - start_time) * 1000)
            is_supported = result != "UNSUPPORTED"
            logger.info(
                f"Translate result: supported={is_supported}, "
                f"yaml_lines={result.count(chr(10)) + 1 if is_supported else 0}, "
                f"time={elapsed_ms}ms"
            )
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
            raise StrategyTranslatorAuthError(
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
            raise StrategyTranslatorError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        try:
            client = anthropic.Anthropic(
                api_key=self._api_key,
                timeout=STRATEGY_TRANSLATOR_TIMEOUT_SECONDS,
                max_retries=STRATEGY_TRANSLATOR_MAX_RETRIES,
            )

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=STRATEGY_TRANSLATOR_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            return message.content[0].text if message.content else ""

        except anthropic.AuthenticationError as e:
            raise StrategyTranslatorAuthError(f"Invalid API key for claude: {e}")
        except anthropic.RateLimitError as e:
            raise StrategyTranslatorRateLimitError(f"Rate limit exceeded: {e}")
        except anthropic.APITimeoutError as e:
            raise StrategyTranslatorTimeoutError(f"Request timed out: {e}")
        except anthropic.APIError as e:
            raise StrategyTranslatorError(f"Claude API error: {e}")

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise StrategyTranslatorError(
                "openai package not installed. Run: pip install openai"
            )

        try:
            client = openai.OpenAI(
                api_key=self._api_key,
                timeout=STRATEGY_TRANSLATOR_TIMEOUT_SECONDS,
                max_retries=STRATEGY_TRANSLATOR_MAX_RETRIES,
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=STRATEGY_TRANSLATOR_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            return response.choices[0].message.content or ""

        except openai.AuthenticationError as e:
            raise StrategyTranslatorAuthError(f"Invalid API key for openai: {e}")
        except openai.RateLimitError as e:
            raise StrategyTranslatorRateLimitError(f"Rate limit exceeded: {e}")
        except openai.APITimeoutError as e:
            raise StrategyTranslatorTimeoutError(f"Request timed out: {e}")
        except openai.APIError as e:
            raise StrategyTranslatorError(f"OpenAI API error: {e}")

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Call Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise StrategyTranslatorError(
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
                    max_output_tokens=STRATEGY_TRANSLATOR_MAX_TOKENS,
                ),
            )

            return response.text if response.text else ""

        except Exception as e:
            error_str = str(e).lower()
            if "invalid api key" in error_str or "api key" in error_str:
                raise StrategyTranslatorAuthError(f"Invalid API key for gemini: {e}")
            if "rate limit" in error_str or "quota" in error_str:
                raise StrategyTranslatorRateLimitError(f"Rate limit exceeded: {e}")
            if "timeout" in error_str:
                raise StrategyTranslatorTimeoutError(f"Request timed out: {e}")
            raise StrategyTranslatorError(f"Gemini API error: {e}")

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Call Ollama API via HTTP."""
        import json
        import urllib.request
        from urllib.error import URLError

        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        model = self._model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

        url = f"{host.rstrip('/')}/api/chat"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": STRATEGY_TRANSLATOR_MAX_TOKENS,
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
                req, timeout=STRATEGY_TRANSLATOR_TIMEOUT_SECONDS
            ) as response:
                result = json.loads(response.read().decode("utf-8"))

            return result.get("message", {}).get("content", "")

        except TimeoutError:
            raise StrategyTranslatorTimeoutError(
                f"Ollama request timed out after {STRATEGY_TRANSLATOR_TIMEOUT_SECONDS}s"
            )
        except URLError as e:
            if "timed out" in str(e).lower():
                raise StrategyTranslatorTimeoutError(f"Ollama request timed out: {e}")
            raise StrategyTranslatorError(
                f"Failed to connect to Ollama at {host}: {e}. "
                "Is Ollama running? Start with: ollama serve"
            )
        except json.JSONDecodeError as e:
            raise StrategyTranslatorError(f"Invalid response from Ollama: {e}")
        except Exception as e:
            raise StrategyTranslatorError(f"Ollama error: {e}")

    def _call_mock(self, system_prompt: str, user_prompt: str) -> str:
        """Return mock response for testing."""
        # Extract strategy name and intent from user prompt
        lines = user_prompt.split("\n")
        intent_line = lines[0] if lines else ""
        name_line = lines[1] if len(lines) > 1 else ""

        # Parse intent
        intent = intent_line.replace('Generate strategy YAML for: "', "").rstrip('"')
        intent_lower = intent.lower()

        # Parse strategy name
        strategy_name = name_line.replace("Strategy name: ", "").strip()
        if not strategy_name:
            strategy_name = "mock_strategy"

        # Check for unsupported intents FIRST
        unsupported_keywords = [
            "predict",
            "always win",
            "guaranteed",
            "for bbca",
            "for bbri",
            "specific stock",
            "explain",
            "what is",
        ]
        if any(kw in intent_lower for kw in unsupported_keywords):
            return "UNSUPPORTED"

        # Mock translations based on keywords
        if "rsi" in intent_lower and ("ema" in intent_lower or "crossover" in intent_lower):
            return self._mock_rsi_ema_combined(strategy_name)

        if "ema crossover" in intent_lower or ("ema" in intent_lower and "crossover" in intent_lower):
            return self._mock_ema_crossover(strategy_name)

        if "rsi" in intent_lower:
            return self._mock_rsi_strategy(strategy_name)

        if "sma" in intent_lower and "crossover" in intent_lower:
            return self._mock_sma_crossover(strategy_name)

        if "atr" in intent_lower:
            return self._mock_atr_strategy(strategy_name)

        if "conservative" in intent_lower:
            return self._mock_conservative_strategy(strategy_name)

        if "momentum" in intent_lower:
            return self._mock_momentum_strategy(strategy_name)

        # Default fallback for testing
        return self._mock_rsi_strategy(strategy_name)

    def _mock_rsi_strategy(self, name: str) -> str:
        """Generate mock RSI oversold/overbought strategy."""
        return f'''version: 1
name: "{name}"
description: "RSI oversold/overbought strategy"

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_oversold
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  - name: rsi_overbought
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
'''

    def _mock_ema_crossover(self, name: str) -> str:
        """Generate mock EMA crossover strategy."""
        return f'''version: 1
name: "{name}"
description: "EMA 9/21 crossover strategy"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

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
    rationale: "Fast EMA above slow EMA indicates bullish momentum"

  - name: bearish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: "<"
      right:
        indicator: slow_ema
    outcome: HIGH_RISK
    rationale: "Fast EMA below slow EMA indicates bearish momentum"
'''

    def _mock_rsi_ema_combined(self, name: str) -> str:
        """Generate mock combined RSI and EMA strategy."""
        return f'''version: 1
name: "{name}"
description: "RSI oversold with EMA crossover confirmation"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_oversold
    priority: 5
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  - name: bullish_ema_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "Fast EMA above slow EMA confirms bullish momentum"

  - name: rsi_overbought
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
'''

    def _mock_sma_crossover(self, name: str) -> str:
        """Generate mock SMA crossover strategy."""
        return f'''version: 1
name: "{name}"
description: "SMA 20/50 crossover strategy"

indicators:
  fast_sma:
    type: SMA
    period: 20
  slow_sma:
    type: SMA
    period: 50

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: golden_cross
    priority: 10
    when:
      left:
        indicator: fast_sma
      operator: ">"
      right:
        indicator: slow_sma
    outcome: LOW_RISK
    rationale: "Golden cross - fast SMA crosses above slow SMA"

  - name: death_cross
    priority: 10
    when:
      left:
        indicator: fast_sma
      operator: "<"
      right:
        indicator: slow_sma
    outcome: HIGH_RISK
    rationale: "Death cross - fast SMA crosses below slow SMA"
'''

    def _mock_atr_strategy(self, name: str) -> str:
        """Generate mock ATR-based strategy."""
        return f'''version: 1
name: "{name}"
description: "ATR volatility-based strategy"

indicators:
  atr_14:
    type: ATR
    period: 14

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: low_volatility
    priority: 10
    when:
      indicator: atr_14
      operator: "<"
      value: 2.0
    outcome: LOW_RISK
    rationale: "Low volatility environment favorable for entries"

  - name: high_volatility
    priority: 10
    when:
      indicator: atr_14
      operator: ">"
      value: 5.0
    outcome: HIGH_RISK
    rationale: "High volatility indicates increased risk"
'''

    def _mock_conservative_strategy(self, name: str) -> str:
        """Generate mock conservative RSI strategy."""
        return f'''version: 1
name: "{name}"
description: "Conservative RSI strategy with strict thresholds"

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: very_oversold
    priority: 5
    when:
      indicator: RSI
      operator: "<"
      value: 25
    outcome: LOW_RISK
    rationale: "RSI below 25 indicates extremely oversold conditions"

  - name: very_overbought
    priority: 5
    when:
      indicator: RSI
      operator: ">"
      value: 75
    outcome: HIGH_RISK
    rationale: "RSI above 75 indicates extremely overbought conditions"
'''

    def _mock_momentum_strategy(self, name: str) -> str:
        """Generate mock momentum strategy."""
        return f'''version: 1
name: "{name}"
description: "Momentum strategy using RSI and EMA"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_momentum
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 40
    outcome: LOW_RISK
    rationale: "RSI below 40 shows potential upside momentum"

  - name: ema_confirmation
    priority: 15
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "EMA crossover confirms bullish momentum"

  - name: exit_signal
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 65
    outcome: HIGH_RISK
    rationale: "RSI above 65 indicates potential reversal"
'''
