"""
ComputeSMA use case - orchestrates SMA calculation over cached candle data.

This use case coordinates between:
- MarketDataRepository (retrieves cached candles)
- SMA indicator (pure calculation)

It implements a read-only analysis pattern.

Layer: Application
Depends on: Domain ports, Domain indicators
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.domain.indicators.sma import PriceField, calculate_sma
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass
class ComputeSMARequest:
    """Request DTO for computing SMA."""

    ticker: str
    period: int = 20
    price_field: PriceField = "close"
    days: int = 365  # How many days of history to load


@dataclass
class ComputeSMAResponse:
    """Response DTO containing SMA calculation results."""

    ticker: str
    period: int
    price_field: str
    values: list[tuple[date, Decimal]]
    candle_count: int
    sma_count: int
    date_range: tuple[date, date] | None

    @property
    def has_values(self) -> bool:
        """Check if any SMA values were calculated."""
        return len(self.values) > 0


class ComputeSMAUseCase:
    """
    Use case for computing SMA over cached market data.

    Flow:
    1. Validate request
    2. Fetch cached candles from repository
    3. Calculate SMA using domain indicator
    4. Return results with metadata

    This use case depends only on ports (interfaces), never on
    concrete implementations.
    """

    def __init__(self, repository: MarketDataRepository) -> None:
        """
        Initialize with repository dependency.

        Args:
            repository: MarketDataRepository for fetching cached candles
        """
        self._repository = repository

    def execute(self, request: ComputeSMARequest) -> ComputeSMAResponse:
        """
        Execute the compute SMA use case.

        Args:
            request: Contains ticker, period, price_field, days

        Returns:
            ComputeSMAResponse with SMA values and metadata

        Raises:
            ValueError: If ticker invalid or period invalid
        """
        # Validate input
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        if request.period < 1:
            raise ValueError("Period must be at least 1")

        # Determine date range for query
        # Use the actual data range from the repository, not an absolute date range
        date_range = self._repository.get_date_range(ticker)
        
        if not date_range:
            # No data available for this ticker
            return ComputeSMAResponse(
                ticker=ticker,
                period=request.period,
                price_field=request.price_field,
                values=[],
                candle_count=0,
                sma_count=0,
                date_range=None,
            )
        
        earliest_date, latest_date = date_range
        
        # Calculate how far back we need to go, but don't go beyond available data
        days_back = min(request.days, (latest_date - earliest_date).days + 1)
        start_date = latest_date - timedelta(days=days_back - 1)
        end_date = latest_date

        # Fetch candles from cache
        candles = self._repository.get_candles(ticker, start_date, end_date)

        # Handle no data case
        if not candles:
            return ComputeSMAResponse(
                ticker=ticker,
                period=request.period,
                price_field=request.price_field,
                values=[],
                candle_count=0,
                sma_count=0,
                date_range=None,
            )

        # Calculate SMA using domain indicator
        sma_values = calculate_sma(
            candles,
            period=request.period,
            price_field=request.price_field,
        )

        # Build response with metadata
        date_range_result = (candles[0].date, candles[-1].date)

        return ComputeSMAResponse(
            ticker=ticker,
            period=request.period,
            price_field=request.price_field,
            values=sma_values,
            candle_count=len(candles),
            sma_count=len(sma_values),
            date_range=date_range_result,
        )
