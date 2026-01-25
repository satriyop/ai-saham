"""
Sentiment infrastructure adapters.

This module provides implementations of the sentiment-related ports:
- NewsProvider: Google News RSS, Mock provider
- HeadlineClassifier: Keyword-based, AI-based

Usage:
    from src.infrastructure.sentiment import SentimentFactory

    # Create news provider (default: google)
    provider = SentimentFactory.create_news_provider()

    # Create classifier (default: keyword)
    classifier = SentimentFactory.create_classifier()

    # Create AI classifier
    classifier = SentimentFactory.create_classifier(use_ai=True)

Layer: Infrastructure
"""

from src.infrastructure.sentiment.factory import SentimentFactory
from src.infrastructure.sentiment.google_news_provider import GoogleNewsProvider
from src.infrastructure.sentiment.keyword_classifier import KeywordClassifier
from src.infrastructure.sentiment.mock_provider import MockNewsProvider

__all__ = [
    "GoogleNewsProvider",
    "KeywordClassifier",
    "MockNewsProvider",
    "SentimentFactory",
]
