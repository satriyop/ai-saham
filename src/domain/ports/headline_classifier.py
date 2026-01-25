"""
Headline classifier port.

Abstract interface for classifying headline sentiment. Infrastructure
layer provides concrete implementations (keyword-based, AI-based, etc.).

Layer: Domain
"""

from typing import Protocol

from src.domain.value_objects.sentiment import Sentiment


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

    def classify(self, headline: str) -> Sentiment:
        """Classify a single headline.

        Args:
            headline: The headline text to classify

        Returns:
            Sentiment classification (POSITIVE, NEUTRAL, or NEGATIVE)
        """
        ...

    def classify_batch(self, headlines: list[str]) -> list[Sentiment]:
        """Classify multiple headlines.

        Default implementation calls classify() for each headline.
        AI implementations may batch for efficiency.

        Args:
            headlines: List of headline texts to classify

        Returns:
            List of Sentiment classifications in same order as input
        """
        ...
