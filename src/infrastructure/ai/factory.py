"""
Explainer factory with rate limiting.

Creates appropriate explainer instances based on configuration.

Layer: Infrastructure
"""

import os
import time

from src.domain.ports.ai_explainer import (
    AIExplainer,
    ExplainerAuthError,
    ExplainerRateLimitError,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment

# Supported providers
SUPPORTED_PROVIDERS = ("claude", "openai", "gemini", "ollama", "mock")
DEFAULT_PROVIDER = "claude"
DEFAULT_RATE_LIMIT = 10  # calls per minute


class RateLimitedExplainer:
    """Wrapper that enforces local rate limiting on any explainer.

    Uses a sliding window to track calls per minute.
    """

    def __init__(self, explainer: AIExplainer, max_per_minute: int):
        """Initialize rate-limited explainer.

        Args:
            explainer: The underlying explainer to wrap
            max_per_minute: Maximum calls allowed per minute (0 = unlimited)
        """
        self._explainer = explainer
        self._max_per_minute = max_per_minute
        self._calls: list[float] = []

    @property
    def provider_name(self) -> str:
        """Return provider name from underlying explainer."""
        if hasattr(self._explainer, "provider_name"):
            return self._explainer.provider_name
        return "unknown"

    def explain_assessment(
        self,
        ticker: str,
        assessment: RiskAssessment,
        snapshot: IndicatorSnapshot,
    ) -> str:
        """Generate explanation with rate limiting."""
        self._enforce_rate_limit()
        return self._explainer.explain_assessment(ticker, assessment, snapshot)

    def _enforce_rate_limit(self) -> None:
        """Check and enforce rate limit.

        Raises:
            ExplainerRateLimitError: If rate limit is exceeded
        """
        if self._max_per_minute <= 0:
            return  # Unlimited

        now = time.time()

        # Remove calls older than 1 minute
        self._calls = [t for t in self._calls if now - t < 60]

        if len(self._calls) >= self._max_per_minute:
            wait_time = 60 - (now - self._calls[0])
            raise ExplainerRateLimitError(
                f"Local rate limit exceeded ({self._max_per_minute}/min). "
                f"Try again in {wait_time:.0f}s"
            )

        self._calls.append(now)


class ExplainerFactory:
    """Factory for creating AI explainer instances."""

    @staticmethod
    def create(
        provider: str | None = None,
        with_rate_limit: bool = True,
        model: str | None = None,
    ) -> AIExplainer:
        """Create an explainer instance based on provider.

        Args:
            provider: Provider name. If None, reads from AI_PROVIDER env var.
                     Supported: claude, openai, gemini, ollama, mock
            with_rate_limit: Whether to wrap with rate limiting (default: True)
            model: Optional model name override (currently used for Ollama)

        Returns:
            An AIExplainer instance

        Raises:
            ExplainerAuthError: If required API key is missing
            ValueError: If provider is not supported
        """
        # Determine provider
        if provider is None:
            provider = os.getenv("AI_PROVIDER", DEFAULT_PROVIDER).lower()
        else:
            provider = provider.lower()

        # Validate provider
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {provider}. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
            )

        # Create provider-specific explainer
        explainer = ExplainerFactory._create_provider(provider, model=model)

        # Optionally wrap with rate limiting
        if with_rate_limit:
            rate_limit = int(os.getenv("AI_RATE_LIMIT", str(DEFAULT_RATE_LIMIT)))
            explainer = RateLimitedExplainer(explainer, rate_limit)

        return explainer

    @staticmethod
    def _create_provider(provider: str, model: str | None = None) -> AIExplainer:
        """Create the provider-specific explainer instance.

        Args:
            provider: Lowercase provider name

        Returns:
            AIExplainer instance
        """
        if provider == "claude":
            from src.infrastructure.ai.claude_explainer import ClaudeExplainer

            return ClaudeExplainer()

        elif provider == "openai":
            from src.infrastructure.ai.openai_explainer import OpenAIExplainer

            return OpenAIExplainer()

        elif provider == "gemini":
            from src.infrastructure.ai.gemini_explainer import GeminiExplainer

            return GeminiExplainer()

        elif provider == "ollama":
            from src.infrastructure.ai.ollama_explainer import OllamaExplainer

            return OllamaExplainer(model=model)

        else:  # mock
            from src.infrastructure.ai.mock_explainer import MockExplainer

            return MockExplainer()

    @staticmethod
    def get_available_providers() -> list[str]:
        """Return list of providers with valid configuration.

        Returns:
            List of provider names that can be created without error
        """
        available = []

        for provider in SUPPORTED_PROVIDERS:
            try:
                ExplainerFactory._create_provider(provider)
                available.append(provider)
            except ExplainerAuthError:
                # Provider needs API key that isn't set
                pass
            except Exception:
                # Provider has other issues
                pass

        return available
