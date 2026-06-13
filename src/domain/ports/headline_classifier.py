"""
Headline classifier port.

Abstract interface for classifying headline sentiment. Infrastructure
layer provides concrete implementations (keyword-based, AI-based, etc.).

Layer: Domain
"""

from typing import Protocol

from src.domain.value_objects.sentiment import Classification


class HeadlineClassifierError(Exception):
    """Base exception for classifier errors."""

    pass


class HeadlineClassifier(Protocol):
    """Port for classifying headline sentiment.

    This is a domain port (interface) that infrastructure adapters
    must implement. The domain layer depends on this abstraction,
    not concrete implementations.
    """

    @property
    def classifier_name(self) -> str:
        """Return the classifier identifier."""
        ...

    def classify(self, ticker: str, headline: str) -> Classification:
        """Classify a single headline.

        Args:
            ticker: The stock ticker to evaluate the headline against
            headline: The headline text to classify

        Returns:
            Classification result containing sentiment and catalyst
        """
        ...

    def classify_batch(self, ticker: str, headlines: list[str]) -> list[Classification]:
        """Classify multiple headlines.

        Default implementation calls classify() for each headline.
        AI implementations may batch for efficiency.

        Args:
            ticker: The stock ticker to evaluate the headlines against
            headlines: List of headline texts to classify

        Returns:
            List of Classification results in same order as input
        """
        ...
