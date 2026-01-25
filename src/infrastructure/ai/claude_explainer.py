"""
Claude (Anthropic) explainer adapter.

Implements AIExplainer port using Claude API.

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


class ClaudeExplainer(BaseExplainer):
    """Anthropic Claude API adapter for explanations."""

    def __init__(self, api_key: str | None = None):
        """Initialize Claude explainer.

        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.

        Raises:
            ExplainerAuthError: If no API key is available.
        """
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ExplainerAuthError(
                "No API key for claude (set ANTHROPIC_API_KEY environment variable)"
            )

    @property
    def provider_name(self) -> str:
        return "claude"

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int]:
        """Call Claude API."""
        try:
            import anthropic
        except ImportError:
            raise ExplainerError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        try:
            client = anthropic.Anthropic(
                api_key=self._api_key,
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=LLM_MAX_RETRIES,
            )

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=LLM_MAX_TOKENS,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )

            text = message.content[0].text if message.content else ""
            total_tokens = message.usage.input_tokens + message.usage.output_tokens

            return text, total_tokens

        except anthropic.AuthenticationError as e:
            raise ExplainerAuthError(f"Invalid API key for claude: {e}")
        except anthropic.RateLimitError as e:
            raise ExplainerRateLimitError(f"Rate limit exceeded: {e}")
        except anthropic.APITimeoutError as e:
            raise ExplainerTimeoutError(f"Request timed out: {e}")
        except anthropic.APIError as e:
            raise ExplainerError(f"Claude API error: {e}")
