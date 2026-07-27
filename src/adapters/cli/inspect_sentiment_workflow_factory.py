"""
Factory for the `saham inspect sentiment` and `saham audit sentiment` workflows.

Layer: Adapter

This module owns concrete infrastructure wiring so analyze_sentiment_commands.py
can stay focused on flag parsing, request construction, execution, and rendering.
"""

from __future__ import annotations

from pathlib import Path

from src.application.use_case.audit_sentiment_use_case import AuditSentimentUseCase
from src.application.use_case.fetch_sentiment_use_case import FetchSentimentUseCase
from src.infrastructure.config.group_mapping_config_loader import create_group_mapping_service
from src.infrastructure.persistence.sentiment_repository import SQLiteSentimentRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory


def create_fetch_sentiment_use_case(
    *,
    db_path: Path,
    news_provider_name: str,
    use_ai: bool,
    provider: str | None,
    model: str | None,
) -> FetchSentimentUseCase:
    """Build the fetch-sentiment use case with CLI infrastructure."""
    news_provider = SentimentFactory.create_news_provider(news_provider_name)
    classifier = SentimentFactory.create_classifier(
        use_ai=use_ai,
        provider=provider,
        model=model,
    )
    group_service = create_group_mapping_service()
    sentiment_repo = SQLiteSentimentRepository(db_path=db_path)

    return FetchSentimentUseCase(
        news_provider=news_provider,
        classifier=classifier,
        group_service=group_service,
        sentiment_repo=sentiment_repo,
    )


def create_audit_sentiment_use_case(*, db_path: Path) -> AuditSentimentUseCase:
    """Build the audit-sentiment use case with CLI infrastructure."""
    sentiment_repo = SQLiteSentimentRepository(db_path=db_path)
    market_repo = SQLiteMarketRepository(db_path=db_path)

    return AuditSentimentUseCase(
        sentiment_repo=sentiment_repo,
        market_repo=market_repo,
    )
