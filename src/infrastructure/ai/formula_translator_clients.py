"""
Provider-specific API transport for formula translation.

Implements the raw HTTP/SDK calls for Claude, OpenAI, Gemini, and Ollama.
Provider SDKs are imported lazily inside each call function so they remain
optional dependencies.

Layer: Infrastructure
"""

import os

from src.application.ports.formula_translator import (
    FormulaTranslatorError,
    TranslatorAuthError,
    TranslatorRateLimitError,
    TranslatorTimeoutError,
)
from src.infrastructure.ai.formula_translator_prompt import (
    FORMULA_TRANSLATOR_MAX_RETRIES,
    FORMULA_TRANSLATOR_MAX_TOKENS,
    FORMULA_TRANSLATOR_TIMEOUT_SECONDS,
)


def call_claude(api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call Claude API."""
    try:
        import anthropic
    except ImportError:
        raise FormulaTranslatorError("anthropic package not installed. Run: pip install anthropic")

    try:
        client = anthropic.Anthropic(
            api_key=api_key,
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


def call_openai(api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI API."""
    try:
        import openai
    except ImportError:
        raise FormulaTranslatorError("openai package not installed. Run: pip install openai")

    try:
        client = openai.OpenAI(
            api_key=api_key,
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


def call_gemini(api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call Gemini API."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise FormulaTranslatorError(
            "google-generativeai package not installed. Run: pip install google-generativeai"
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


def call_ollama(model: str | None, system_prompt: str, user_prompt: str) -> str:
    """Call Ollama API via HTTP."""
    import json
    import urllib.request
    from urllib.error import URLError

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

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
        with urllib.request.urlopen(req, timeout=FORMULA_TRANSLATOR_TIMEOUT_SECONDS) as response:
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


def call_formula_translator_provider(
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
    raise FormulaTranslatorError(f"Unknown provider for client dispatch: {provider}")
