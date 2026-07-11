"""
Provider-specific API transport for strategy translation.

Implements the raw HTTP/SDK calls for Claude, OpenAI, Gemini, and Ollama.
Provider SDKs are imported lazily inside each call function so they remain
optional dependencies.

Layer: Infrastructure
"""

import os

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
)


def call_claude(api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call Claude API."""
    try:
        import anthropic
    except ImportError:
        raise StrategyTranslatorError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    try:
        client = anthropic.Anthropic(
            api_key=api_key,
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


def call_openai(api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI API."""
    try:
        import openai
    except ImportError:
        raise StrategyTranslatorError(
            "openai package not installed. Run: pip install openai"
        )

    try:
        client = openai.OpenAI(
            api_key=api_key,
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


def call_gemini(api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call Gemini API."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise StrategyTranslatorError(
            "google-generativeai package not installed. "
            "Run: pip install google-generativeai"
        )

    try:
        genai.configure(api_key=api_key)

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


def call_ollama(model: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call Ollama API via HTTP."""
    import json
    import urllib.request
    from urllib.error import URLError

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

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


def call_strategy_translator_provider(
    *,
    provider: str,
    api_key: str | None,
    model: str | None,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Dispatch a translation call to the given real (non-mock) provider."""
    if provider == "claude":
        return call_claude(api_key, system_prompt, user_prompt)
    elif provider == "openai":
        return call_openai(api_key, system_prompt, user_prompt)
    elif provider == "gemini":
        return call_gemini(api_key, system_prompt, user_prompt)
    elif provider == "ollama":
        return call_ollama(model, system_prompt, user_prompt)
    raise StrategyTranslatorError(f"Unknown provider for client dispatch: {provider}")
