"""
Provider transport for the AI headline classifier.

Handles provider-specific client creation and API calls. SDK imports are
lazy (deferred to client creation) so unused providers never require their
package to be installed.

Layer: Infrastructure
"""

import os

from src.domain.ports.headline_classifier import HeadlineClassifierError
from src.infrastructure.sentiment.ai_classifier_prompts import SYSTEM_PROMPT

LLM_TIMEOUT_SECONDS = 10
LLM_MAX_TOKENS = 60

SUPPORTED_AI_CLASSIFIER_PROVIDERS = ("deepseek", "claude", "openai", "gemini", "ollama")


def _create_deepseek_client(model: str | None = None):
    """Create DeepSeek client (using OpenAI SDK)."""
    try:
        import openai

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HeadlineClassifierError("DEEPSEEK_API_KEY not set")
        # DeepSeek uses OpenAI-compatible API
        return openai.OpenAI(
            api_key=api_key, base_url="https://api.deepseek.com", timeout=LLM_TIMEOUT_SECONDS
        )
    except ImportError:
        raise HeadlineClassifierError("openai package not installed (required for DeepSeek)")


def _create_claude_client(model: str | None = None):
    """Create Claude client."""
    try:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise HeadlineClassifierError("ANTHROPIC_API_KEY not set")
        return anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
    except ImportError:
        raise HeadlineClassifierError("anthropic package not installed")


def _create_openai_client(model: str | None = None):
    """Create OpenAI client."""
    try:
        import openai

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HeadlineClassifierError("OPENAI_API_KEY not set")
        return openai.OpenAI(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
    except ImportError:
        raise HeadlineClassifierError("openai package not installed")


def _create_gemini_client(model: str | None = None):
    """Create Gemini client."""
    try:
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HeadlineClassifierError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model or "gemini-1.5-flash")
    except ImportError:
        raise HeadlineClassifierError("google-generativeai package not installed")


def _create_ollama_client(model: str | None = None):
    """Create Ollama client (returns dict with config)."""
    try:
        import ollama

        return {
            "client": ollama,
            "model": model or os.getenv("OLLAMA_MODEL", "llama3.2"),
        }
    except ImportError:
        raise HeadlineClassifierError("ollama package not installed")


def _call_deepseek(client, user_prompt: str, model: str | None = None) -> str:
    """Call DeepSeek API."""
    response = client.chat.completions.create(
        model=model or "deepseek-chat",  # Default model
        max_tokens=LLM_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _call_claude(client, user_prompt: str, model: str | None = None) -> str:
    """Call Claude API."""
    response = client.messages.create(
        model="claude-3-haiku-20240307",  # Fast model for classification
        max_tokens=LLM_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _call_openai(client, user_prompt: str, model: str | None = None) -> str:
    """Call OpenAI API."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Fast model for classification
        max_tokens=LLM_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _call_gemini(client, user_prompt: str, model: str | None = None) -> str:
    """Call Gemini API."""
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
    response = client.generate_content(full_prompt)
    return response.text


def _call_ollama(config: dict, user_prompt: str, model: str | None = None) -> str:
    """Call Ollama local API."""
    client = config["client"]
    resolved_model = config["model"]
    response = client.chat(
        model=resolved_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response["message"]["content"]


_CLIENT_FACTORIES = {
    "deepseek": _create_deepseek_client,
    "claude": _create_claude_client,
    "openai": _create_openai_client,
    "gemini": _create_gemini_client,
    "ollama": _create_ollama_client,
}

_CALLERS = {
    "deepseek": _call_deepseek,
    "claude": _call_claude,
    "openai": _call_openai,
    "gemini": _call_gemini,
    "ollama": _call_ollama,
}


class AIClassifierProviderClientFactory:
    """Creates provider-specific AI clients."""

    @staticmethod
    def create(provider: str, model: str | None = None) -> object:
        return create_ai_classifier_client(provider, model)


def create_ai_classifier_client(provider: str, model: str | None = None) -> object:
    """Create a provider-specific client for the given AI provider."""
    factory = _CLIENT_FACTORIES.get(provider)
    if factory is None:
        raise HeadlineClassifierError(f"Unsupported AI provider: {provider}")
    return factory(model)


def call_ai_classifier_provider(
    provider: str, client: object, user_prompt: str, model: str | None = None
) -> str:
    """Call the given AI provider's API and return the raw response text."""
    caller = _CALLERS.get(provider)
    if caller is None:
        raise HeadlineClassifierError(f"Unsupported provider: {provider}")
    return caller(client, user_prompt, model)
