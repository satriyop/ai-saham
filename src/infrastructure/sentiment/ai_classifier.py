"""
AI-based headline classifier.

Uses LLM to classify headline sentiment. Optional enhancement
over the default keyword classifier.

Layer: Infrastructure
"""

import logging
import time

from src.domain.value_objects.sentiment import CatalystType, Classification, Sentiment
from src.infrastructure.ai.provider_config import resolve_ai_provider
from src.infrastructure.sentiment.ai_classifier_prompts import build_user_prompt
from src.infrastructure.sentiment.ai_classifier_providers import (
    call_ai_classifier_provider,
    create_ai_classifier_client,
)
from src.infrastructure.sentiment.ai_classifier_response_parser import (
    parse_ai_classification_response,
)

logger = logging.getLogger("ai_saham.sentiment")


class AIClassifier:
    """AI-based headline classifier using LLM.

    Optional classifier that provides nuanced sentiment and catalyst
    analysis compared to keyword matching. Falls back to NEUTRAL|GENERAL on any error.

    Reuses existing AI infrastructure for consistency and rate limiting.

    Usage:
        classifier = AIClassifier()
        result = classifier.classify("BBCA", "BBCA laba naik 20%")
        # Returns Classification(sentiment=Sentiment.POSITIVE, catalyst=CatalystType.EARNINGS)
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        """Initialize AI classifier.

        Args:
            provider: AI provider name (deepseek, claude, openai, gemini, ollama)
                     If None, reads from AI_PROVIDER env var.
            model: Optional model override
        """
        self._provider = provider
        self._model = model
        self._client = None  # Lazy initialization

    def _resolve_provider(self) -> str:
        return resolve_ai_provider(self._provider)

    @property
    def classifier_name(self) -> str:
        """Return classifier identifier."""
        return f"ai:{self._resolve_provider()}"

    def classify(self, ticker: str, headline: str) -> Classification:
        """Classify headline using AI.

        Args:
            ticker: The stock ticker to evaluate the headline against
            headline: The headline text to classify

        Returns:
            Classification result. Returns NEUTRAL|GENERAL on any error.
        """
        try:
            response = self._call_ai(ticker, headline)
            return parse_ai_classification_response(response)
        except Exception as e:
            logger.warning(f"AI classification failed, defaulting to NEUTRAL|GENERAL: {e}")
            return Classification(Sentiment.NEUTRAL, CatalystType.GENERAL)

    def classify_batch(self, ticker: str, headlines: list[str]) -> list[Classification]:
        """Classify multiple headlines.

        Args:
            ticker: The stock ticker
            headlines: List of headline texts to classify

        Returns:
            List of Classification results in same order
        """
        return [self.classify(ticker, h) for h in headlines]

    def _get_client(self):
        """Lazy initialize the AI client.

        Uses provider-specific client for efficiency.
        Falls back to default provider if not specified.
        """
        if self._client is not None:
            return self._client

        provider = self._resolve_provider()
        self._client = create_ai_classifier_client(provider, self._model)
        return self._client

    def _call_ai(self, ticker: str, headline: str) -> str:
        """Call AI provider for classification.

        Args:
            ticker: Stock ticker symbol
            headline: Headline text (truncated to 500 chars)

        Returns:
            Raw AI response text
        """
        # Truncate long headlines
        headline = headline[:500]
        user_prompt = build_user_prompt(ticker, headline)

        provider = self._resolve_provider()

        start_time = time.time()
        logger.debug(f"AI classify request: provider={provider}")

        try:
            client = self._get_client()
            response = call_ai_classifier_provider(provider, client, user_prompt, self._model)

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"AI classify response: time={elapsed_ms}ms")

            return response

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"AI classify error after {elapsed_ms}ms: {e}")
            raise
