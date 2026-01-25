"""
Google Gemini explainer adapter.

Implements AIExplainer port using Google Generative AI API.

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
    LLM_MAX_TOKENS,
    LLM_TIMEOUT_SECONDS,
    BaseExplainer,
)


class GeminiExplainer(BaseExplainer):
    """Google Gemini API adapter for explanations."""

    def __init__(self, api_key: str | None = None):
        """Initialize Gemini explainer.

        Args:
            api_key: Google API key. If None, reads from GOOGLE_API_KEY env var.

        Raises:
            ExplainerAuthError: If no API key is available.
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ExplainerAuthError(
                "No API key for gemini (set GOOGLE_API_KEY environment variable)"
            )

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int]:
        """Call Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ExplainerError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        try:
            genai.configure(api_key=self._api_key)

            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=system_prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=LLM_MAX_TOKENS,
                ),
            )

            # Set timeout via request options
            response = model.generate_content(
                user_prompt,
                request_options={"timeout": LLM_TIMEOUT_SECONDS},
            )

            text = response.text if response.text else ""

            # Gemini returns usage metadata differently
            total_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                total_tokens = (
                    getattr(response.usage_metadata, "prompt_token_count", 0) +
                    getattr(response.usage_metadata, "candidates_token_count", 0)
                )

            return text, total_tokens

        except Exception as e:
            error_str = str(e).lower()

            if "api key" in error_str or "authentication" in error_str:
                raise ExplainerAuthError(f"Invalid API key for gemini: {e}")
            elif "quota" in error_str or "rate" in error_str:
                raise ExplainerRateLimitError(f"Rate limit exceeded: {e}")
            elif "timeout" in error_str or "deadline" in error_str:
                raise ExplainerTimeoutError(f"Request timed out: {e}")
            else:
                raise ExplainerError(f"Gemini API error: {e}")
