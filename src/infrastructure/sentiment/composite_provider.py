"""
Composite news provider.

Orchestrates multiple underlying news providers concurrently.
Implements a tiered fallback strategy and deduplication to ensure
high-quality, non-redundant sentiment data.

Layer: Infrastructure
"""

import concurrent.futures
import logging
from typing import List

from src.domain.ports.news_provider import NewsProvider, RawHeadline
from src.infrastructure.sentiment.cnbc_indonesia_provider import CNBCIndonesiaNewsProvider
from src.infrastructure.sentiment.deduplication import deduplicate_headlines
from src.infrastructure.sentiment.google_news_provider import GoogleNewsProvider
from src.infrastructure.sentiment.kontan_provider import KontanNewsProvider

logger = logging.getLogger("ai_saham.sentiment.composite")


class CompositeNewsProvider(NewsProvider):
    """Aggregates news from multiple sources with deduplication and fallback.

    Tier 1 (Premium): Fetches from Kontan and CNBC Indonesia concurrently.
    Tier 2 (Fallback): Fetches from Google News if Tier 1 yields too few results.
    """

    def __init__(self, fallback_threshold: int = 5):
        """Initialize composite provider.

        Args:
            fallback_threshold: If Tier 1 produces fewer deduplicated headlines
                                than this threshold, Tier 2 (Google) is triggered.
        """
        self._fallback_threshold = fallback_threshold

        # Instantiate underlying providers
        self._kontan = KontanNewsProvider()
        self._cnbc = CNBCIndonesiaNewsProvider()
        self._google = GoogleNewsProvider()

    @property
    def provider_name(self) -> str:
        return "composite_aggregator"

    def fetch_headlines(
        self, ticker: str, max_headlines: int = 20, days: int = 3
    ) -> List[RawHeadline]:
        """Fetch and aggregate headlines using a tiered strategy.

        Args:
            ticker: Stock ticker
            max_headlines: Maximum target headlines
            days: Days to look back

        Returns:
            Deduplicated list of headlines
        """
        pooled_headlines: List[RawHeadline] = []

        # TIER 1: Concurrent fetch from premium local sources
        tier1_providers = [self._kontan, self._cnbc]

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tier1_providers)) as executor:
            future_to_provider = {
                executor.submit(p.fetch_headlines, ticker, max_headlines, days): p
                for p in tier1_providers
            }

            for future in concurrent.futures.as_completed(future_to_provider):
                provider = future_to_provider[future]
                try:
                    results = future.result()
                    pooled_headlines.extend(results)
                    logger.debug(f"Fetched {len(results)} headlines from {provider.provider_name}")
                except Exception as e:
                    logger.warning(f"Error fetching from {provider.provider_name}: {e}")

        # Deduplicate Tier 1 results
        deduplicated = deduplicate_headlines(pooled_headlines)
        logger.debug(f"Tier 1 complete: {len(deduplicated)} deduplicated headlines")

        # TIER 2: Fallback to Google News if coverage is low
        if len(deduplicated) < self._fallback_threshold:
            logger.info(f"Tier 1 yielded {len(deduplicated)} results (< {self._fallback_threshold}). Triggering Tier 2 (Google News).")
            try:
                google_results = self._google.fetch_headlines(ticker, max_headlines, days)
                pooled_headlines.extend(google_results)
                logger.debug(f"Fetched {len(google_results)} headlines from {self._google.provider_name}")
            except Exception as e:
                logger.warning(f"Error fetching from {self._google.provider_name}: {e}")

            # Deduplicate the combined pool (Tier 1 + Tier 2)
            deduplicated = deduplicate_headlines(pooled_headlines)
            logger.debug(f"Tier 1 + Tier 2 complete: {len(deduplicated)} deduplicated headlines")

        # Sort by date (newest first) and limit to max_headlines
        deduplicated.sort(key=lambda x: x.published, reverse=True)
        return deduplicated[:max_headlines]
