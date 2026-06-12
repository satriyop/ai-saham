"""
Fetch sentiment use case.

Orchestrates news fetching and sentiment classification to produce
a SentimentSnapshot for a given ticker.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Optional

from src.application.services.group_mapping import GroupMappingService
from src.domain.ports.headline_classifier import HeadlineClassifier
from src.domain.ports.news_provider import NewsProvider
from src.domain.ports.sentiment_repository import SentimentLog, SentimentRepository
from src.domain.value_objects.sentiment import (
    CatalystType,
    HeadlineResult,
    SentimentSnapshot,
)


@dataclass
class FetchSentimentRequest:
    """Request DTO for fetching sentiment.

    Attributes:
        ticker: Stock ticker symbol (will be uppercased)
        max_headlines: Maximum headlines to fetch (default: 20)
        days: Number of days to look back (default: 3)
    """

    ticker: str
    max_headlines: int = 20
    days: int = 3


@dataclass
class FetchSentimentResponse:
    """Response DTO for sentiment fetch.

    Attributes:
        ticker: Normalized ticker symbol (uppercase)
        snapshot: Aggregated sentiment snapshot
        provider: Name of news provider used
        classifier: Name of classifier used
        success: Whether fetch succeeded
        warning: Optional warning message (e.g., no news found)
        from_cache: Whether result was served from cache
    """

    ticker: str
    snapshot: SentimentSnapshot
    provider: str
    classifier: str
    success: bool
    warning: str | None = None
    from_cache: bool = False

    @property
    def has_headlines(self) -> bool:
        """Whether any headlines were found."""
        return self.snapshot.total_count > 0


class FetchSentimentUseCase:
    """Orchestrates news fetching and sentiment classification.

    This use case:
    1. Checks in-memory cache for today's result
    2. Fetches headlines from news provider
    3. Classifies each headline using classifier
    4. Aggregates results into SentimentSnapshot
    5. Caches result for the session

    Cache Strategy:
    - In-memory cache keyed by (ticker, date)
    - Cache cleared on process restart (session-only)
    - No disk persistence to keep it simple

    Usage:
        use_case = FetchSentimentUseCase(
            news_provider=GoogleNewsProvider(),
            classifier=KeywordClassifier(),
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))
        if response.success:
            print(f"Overall: {response.snapshot.overall_sentiment.value}")
    """

    # Class-level in-memory cache: (ticker, date) -> SentimentSnapshot
    _cache: ClassVar[dict[tuple[str, date], SentimentSnapshot]] = {}

    def __init__(
        self,
        news_provider: NewsProvider,
        classifier: HeadlineClassifier,
        group_service: Optional[GroupMappingService] = None,
        sentiment_repo: Optional[SentimentRepository] = None,
    ):
        """Initialize use case with dependencies.

        Args:
            news_provider: News provider implementation
            classifier: Headline classifier implementation
            group_service: Optional service for group propagation
            sentiment_repo: Optional repository for persisting sentiment logs
        """
        self._news_provider = news_provider
        self._classifier = classifier
        self._group_service = group_service
        self._sentiment_repo = sentiment_repo

    def execute(self, request: FetchSentimentRequest) -> FetchSentimentResponse:
        """Fetch and classify news headlines for a ticker.

        Args:
            request: Request with ticker and fetch parameters

        Returns:
            Response with sentiment snapshot and metadata
        """
        ticker = request.ticker.upper()
        today = date.today()

        # Check cache first
        cache_key = (ticker, today)
        if cache_key in self._cache:
            return FetchSentimentResponse(
                ticker=ticker,
                snapshot=self._cache[cache_key],
                provider=self._get_provider_name(),
                classifier=self._get_classifier_name(),
                success=True,
                from_cache=True,
            )

        # Fetch headlines from provider for ticker
        raw_headlines = self._news_provider.fetch_headlines(
            ticker=ticker,
            max_headlines=request.max_headlines,
            days=request.days,
        )

        # Optional Phase 2: Group Propagation
        if self._group_service:
            group_id = self._group_service.get_group_id(ticker)
            if group_id:
                group_info = self._group_service.get_group_info(group_id)
                if group_info:
                    # Fetch top news for the group name
                    group_headlines = self._news_provider.fetch_headlines(
                        ticker=group_info["name"],
                        max_headlines=5,  # Fewer headlines for group context
                        days=request.days,
                    )
                    raw_headlines.extend(group_headlines)

        # Handle no news found
        if not raw_headlines:
            snapshot = SentimentSnapshot.empty(ticker)
            return FetchSentimentResponse(
                ticker=ticker,
                snapshot=snapshot,
                provider=self._get_provider_name(),
                classifier=self._get_classifier_name(),
                success=True,
                warning=f"No recent news found for {ticker}",
            )

        # Classify headlines
        classifications = self._classifier.classify_batch([h.title for h in raw_headlines])

        # Build classified results
        results = [
            HeadlineResult(
                title=raw.title,
                source=raw.source,
                published=raw.published,
                sentiment=c.sentiment,
                catalyst=c.catalyst,
                url=raw.url,
            )
            for raw, c in zip(raw_headlines, classifications)
        ]

        # Create snapshot with majority vote aggregation
        snapshot = SentimentSnapshot.from_headlines(ticker, results)

        # Optional Phase 3: Persist Log for Auditing
        if self._sentiment_repo:
            try:
                # Determine primary catalyst by majority
                cat_counts = {}
                for r in results:
                    cat_counts[r.catalyst] = cat_counts.get(r.catalyst, 0) + 1
                primary_catalyst = max(cat_counts, key=cat_counts.get) if cat_counts else CatalystType.GENERAL

                self._sentiment_repo.save_log(SentimentLog(
                    id=None,
                    date=today,
                    ticker=ticker,
                    sentiment=snapshot.overall_sentiment,
                    catalyst=primary_catalyst,
                    score=float(snapshot.confidence_pct) / 100.0
                ))
            except Exception:
                pass  # Logging is secondary to the immediate result

        # Cache result for this session
        self._cache[cache_key] = snapshot

        return FetchSentimentResponse(
            ticker=ticker,
            snapshot=snapshot,
            provider=self._get_provider_name(),
            classifier=self._get_classifier_name(),
            success=True,
        )

    def _get_provider_name(self) -> str:
        """Get provider name for logging/display."""
        if hasattr(self._news_provider, "provider_name"):
            return self._news_provider.provider_name
        return "unknown"

    def _get_classifier_name(self) -> str:
        """Get classifier name for logging/display."""
        if hasattr(self._classifier, "classifier_name"):
            return self._classifier.classifier_name
        return "unknown"

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the in-memory cache.

        Useful for testing or forcing fresh fetches.
        """
        cls._cache.clear()
