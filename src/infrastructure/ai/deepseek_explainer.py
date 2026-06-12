"""
DeepSeek explainer adapter.

Implements AIExplainer port using DeepSeek API (via OpenAI SDK).

Layer: Infrastructure
"""

import os

from src.domain.ports.ai_explainer import (
    ExplainerAuthError,
    ExplainerError,
    ExplainerRateLimitError,
    ExplainerTimeoutError,
)
from src.infrastructure.ai.base_explainer import (
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT_SECONDS,
    BaseExplainer,
)


class DeepSeekExplainer(BaseExplainer):
    """DeepSeek API adapter for explanations."""

    def __init__(self, api_key: str | None = None):
        """Initialize DeepSeek explainer.

        Args:
            api_key: DeepSeek API key. If None, reads from DEEPSEEK_API_KEY env var.

        Raises:
            ExplainerAuthError: If no API key is available.
        """
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise ExplainerAuthError(
                "No API key for deepseek (set DEEPSEEK_API_KEY environment variable)"
            )

    @property
    def provider_name(self) -> str:
        return "deepseek"

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int]:
        """Call DeepSeek API."""
        try:
            import openai
        except ImportError:
            raise ExplainerError("openai package not installed. Run: pip install openai")

        try:
            client = openai.OpenAI(
                api_key=self._api_key,
                base_url="https://api.deepseek.com",
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=LLM_MAX_RETRIES,
            )

            response = client.chat.completions.create(
                model="deepseek-chat",
                max_tokens=LLM_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            text = response.choices[0].message.content or ""
            total_tokens = response.usage.total_tokens if response.usage else 0

            return text, total_tokens

        except openai.AuthenticationError as e:
            raise ExplainerAuthError(f"Invalid API key for deepseek: {e}")
        except openai.RateLimitError as e:
            raise ExplainerRateLimitError(f"Rate limit exceeded: {e}")
        except openai.APITimeoutError as e:
            raise ExplainerTimeoutError(f"Request timed out: {e}")
        except openai.APIError as e:
            raise ExplainerError(f"DeepSeek API error: {e}")
