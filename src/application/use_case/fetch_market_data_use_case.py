"""
FetchMarketData use case - orchestrates fetching and caching market data.

This use case coordinates between:
- MarketDataProvider (fetches from external source)
- MarketDataRepository (local cache)

It implements the cache-first strategy with optional refresh.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import MarketDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass
class FetchMarketDataRequest:
    """Request DTO for fetching market data."""

    ticker: str
    days: int = 365
    refresh: bool = False


@dataclass
class FetchMarketDataResponse:
    """Response DTO containing fetched market data."""

    ticker: str
    candles: list[Candle]
    source: str  # 'cache' or 'provider'
    date_range: tuple[date, date] | None

    @property
    def count(self) -> int:
        return len(self.candles)


class FetchMarketDataUseCase:
    """
    Use case for fetching market data with cache-first strategy.

    Flow:
    1. If refresh=False and cache has data, return from cache
    2. Otherwise, fetch from provider
    3. Save to cache
    4. Return data

    This use case depends only on ports (interfaces), never on
    concrete implementations.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        repository: MarketDataRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(self, request: FetchMarketDataRequest) -> FetchMarketDataResponse:
        """
        Execute the fetch market data use case.

        Args:
            request: Contains ticker, days, and refresh flag.

        Returns:
            FetchMarketDataResponse with candles and metadata.

        Raises:
            ValueError: If ticker is invalid.
            MarketDataProviderError: If fetch fails.
            MarketDataRepositoryError: If cache operations fail.
        """
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        end_date = date.today()
        start_date = end_date - timedelta(days=request.days)

        # Check cache first (unless refresh requested)
        if not request.refresh:
            cached_range = self._repository.get_date_range(ticker)
            if cached_range and self._covers_range(cached_range, start_date, end_date):
                candles = self._repository.get_candles(ticker, start_date, end_date)
                if candles:
                    return FetchMarketDataResponse(
                        ticker=ticker,
                        candles=candles,
                        source="cache",
                        date_range=(candles[0].date, candles[-1].date),
                    )

        # Fetch from provider
        candles = self._provider.fetch_daily_ohlcv(ticker, start_date, end_date)

        # Save to cache
        if candles:
            self._repository.save_candles(candles)

        date_range = (candles[0].date, candles[-1].date) if candles else None

        return FetchMarketDataResponse(
            ticker=ticker,
            candles=candles,
            source="provider",
            date_range=date_range,
        )

    def _covers_range(
        self,
        cached_range: tuple[date, date],
        start_date: date,
        end_date: date,
    ) -> bool:
        """Check if cached range covers the requested range."""
        cached_start, cached_end = cached_range
        return cached_start <= start_date and cached_end >= end_date - timedelta(days=7)
