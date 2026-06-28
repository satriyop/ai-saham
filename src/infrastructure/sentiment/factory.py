"""
Sentiment factory.

Factory for creating news providers and headline classifiers.
Centralizes instantiation logic and configuration.

Layer: Infrastructure
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.ports.headline_classifier import HeadlineClassifier
    from src.domain.ports.news_provider import NewsProvider

# Supported providers
SUPPORTED_NEWS_PROVIDERS = ("composite", "google", "kontan", "cnbc", "idxchannel", "mock")
SUPPORTED_CLASSIFIERS = ("keyword", "ai")
DEFAULT_NEWS_PROVIDER = "composite"
DEFAULT_CLASSIFIER = "keyword"


class SentimentFactory:
    """Factory for creating sentiment providers and classifiers.

    Centralizes the creation of news providers and classifiers
    based on configuration. Follows the same pattern as ExplainerFactory.

    Usage:
        # Create news provider (default: google)
        provider = SentimentFactory.create_news_provider()

        # Create mock provider for testing
        provider = SentimentFactory.create_news_provider("mock")

        # Create keyword classifier (default)
        classifier = SentimentFactory.create_classifier()

        # Create AI classifier
        classifier = SentimentFactory.create_classifier(use_ai=True)
    """

    @staticmethod
    def create_news_provider(provider: str | None = None) -> "NewsProvider":
        """Create news provider instance.

        Args:
            provider: Provider name. If None, reads from NEWS_PROVIDER env var.
                     Supported: google, mock

        Returns:
            NewsProvider implementation

        Raises:
            ValueError: If provider is not supported
        """
        provider = (provider or os.getenv("NEWS_PROVIDER", DEFAULT_NEWS_PROVIDER)).lower()

        if provider not in SUPPORTED_NEWS_PROVIDERS:
            raise ValueError(
                f"Unsupported news provider: {provider}. "
                f"Supported: {', '.join(SUPPORTED_NEWS_PROVIDERS)}"
            )

        if provider == "composite":
            from src.infrastructure.sentiment.composite_provider import CompositeNewsProvider

            return CompositeNewsProvider()
        elif provider == "mock":
            from src.infrastructure.sentiment.mock_provider import MockNewsProvider

            return MockNewsProvider()
        elif provider == "kontan":
            from src.infrastructure.sentiment.kontan_provider import KontanNewsProvider

            return KontanNewsProvider()
        elif provider == "cnbc":
            from src.infrastructure.sentiment.cnbc_indonesia_provider import (
                CNBCIndonesiaNewsProvider,
            )

            return CNBCIndonesiaNewsProvider()
        elif provider == "idxchannel":
            from src.infrastructure.sentiment.idxchannel_provider import (
                IDXChannelNewsProvider,
            )

            return IDXChannelNewsProvider()
        else:  # google
            from src.infrastructure.sentiment.google_news_provider import (
                GoogleNewsProvider,
            )

            return GoogleNewsProvider()

    @staticmethod
    def create_classifier(
        use_ai: bool = False,
        provider: str | None = None,
        model: str | None = None,
    ) -> "HeadlineClassifier":
        """Create headline classifier instance.

        Args:
            use_ai: Whether to use AI classifier (default: False = keyword)
            provider: AI provider name (only used if use_ai=True)
            model: AI model override (only used if use_ai=True)

        Returns:
            HeadlineClassifier implementation
        """
        if use_ai:
            from src.infrastructure.sentiment.ai_classifier import AIClassifier

            return AIClassifier(provider=provider, model=model)
        else:
            from src.infrastructure.sentiment.keyword_classifier import (
                KeywordClassifier,
            )

            return KeywordClassifier()

    @staticmethod
    def get_available_providers() -> list[str]:
        """Return list of available news providers.

        Returns:
            List of provider names that can be instantiated
        """
        available = []

        for provider in SUPPORTED_NEWS_PROVIDERS:
            try:
                SentimentFactory.create_news_provider(provider)
                available.append(provider)
            except Exception:
                pass

        return available

    @staticmethod
    def get_available_classifiers() -> list[str]:
        """Return list of available classifiers.

        Returns:
            List of classifier types that can be instantiated
        """
        available = ["keyword"]  # Always available

        # Check if AI is available
        try:
            from src.infrastructure.ai import ExplainerFactory

            ai_providers = ExplainerFactory.get_available_providers()
            if ai_providers:
                available.append("ai")
        except Exception:
            pass

        return available
