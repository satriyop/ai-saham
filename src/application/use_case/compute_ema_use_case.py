"""
ComputeEMA use case - orchestrates EMA calculation with warm-up buffer handling.

This use case coordinates between:
- MarketDataRepository (retrieves cached candles)
- EMA indicator (pure calculation)

It implements a read-only analysis pattern with professional-grade
warm-up buffer handling to ensure converged EMA values.

Layer: Application
Depends on: Domain ports, Domain indicators
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.domain.indicators.ema import PriceField, calculate_ema
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass
class ComputeEMARequest:
    """Request DTO for computing EMA."""

    ticker: str
    period: int = 20
    price_field: PriceField = "close"
    days: int = 365  # How many days of history to return


_COVERAGE_TOLERANCE_DAYS = 7  # acceptable shortfall before emitting a warning


@dataclass
class ComputeEMAResponse:
    """Response DTO containing EMA calculation results."""

    ticker: str
    period: int
    price_field: str
    values: list[tuple[date, Decimal]]
    candle_count: int
    ema_count: int
    date_range: tuple[date, date] | None
    coverage_warning: str | None = None

    @property
    def has_values(self) -> bool:
        """Check if any EMA values were calculated."""
        return len(self.values) > 0


class ComputeEMAUseCase:
    """
    Use case for computing EMA over cached market data.

    Implements professional-grade warm-up buffer handling:
    1. Over-fetches candles by 2× period (warm-up buffer)
    2. Calculates EMA over full dataset
    3. Slices off warm-up region
    4. Returns only converged values within user's requested window

    This ensures the returned EMA values have converged and are
    not influenced by the SMA seed.

    Flow:
    1. Validate request
    2. Over-fetch candles (requested days + warm-up buffer)
    3. Calculate EMA using domain indicator
    4. Slice off warm-up region
    5. Return converged results with metadata
    """

    # Multiplier for warm-up period (2× period is standard for EMA convergence)
    WARM_UP_MULTIPLIER = 2

    def __init__(self, repository: MarketDataRepository) -> None:
        """
        Initialize with repository dependency.

        Args:
            repository: MarketDataRepository for fetching cached candles
        """
        self._repository = repository

    def execute(self, request: ComputeEMARequest) -> ComputeEMAResponse:
        """
        Execute the compute EMA use case.

        Args:
            request: Contains ticker, period, price_field, days

        Returns:
            ComputeEMAResponse with EMA values and metadata

        Raises:
            ValueError: If ticker invalid or period invalid
        """
        # Validate input
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        if request.period < 1:
            raise ValueError("Period must be at least 1")

        # Determine date range from the repository
        date_range = self._repository.get_date_range(ticker)

        if not date_range:
            # No data available for this ticker
            return ComputeEMAResponse(
                ticker=ticker,
                period=request.period,
                price_field=request.price_field,
                values=[],
                candle_count=0,
                ema_count=0,
                date_range=None,
            )

        earliest_date, latest_date = date_range

        available_days = (latest_date - earliest_date).days + 1
        coverage_warning: str | None = None
        if available_days < request.days - _COVERAGE_TOLERANCE_DAYS:
            coverage_warning = (
                f"Only {available_days}d cached, {request.days}d requested. "
                f"Run: saham fetch market {ticker} --days {request.days}"
            )

        # Calculate warm-up buffer (2× period for EMA convergence)
        warm_up_days = request.period * self.WARM_UP_MULTIPLIER

        # Calculate how far back we need to go, but don't go beyond available data
        total_days_needed = min(request.days + warm_up_days, available_days)
        fetch_start_date = latest_date - timedelta(days=total_days_needed - 1)

        # User cutoff: after excluding warm-up buffer
        user_cutoff_date = latest_date - timedelta(days=request.days - 1)

        # Fetch candles from cache (over-fetched to include warm-up region)
        candles = self._repository.get_candles(ticker, fetch_start_date, latest_date)

        # Handle no data case
        if not candles:
            return ComputeEMAResponse(
                ticker=ticker,
                period=request.period,
                price_field=request.price_field,
                values=[],
                candle_count=0,
                ema_count=0,
                date_range=None,
            )

        # Calculate EMA using domain indicator (includes warm-up region)
        full_ema_values = calculate_ema(
            candles,
            period=request.period,
            price_field=request.price_field,
        )

        # Slice off warm-up region: keep only values >= user_cutoff_date
        converged_values = [(d, v) for d, v in full_ema_values if d >= user_cutoff_date]

        # Calculate date range of returned values
        if converged_values:
            date_range_result = (converged_values[0][0], converged_values[-1][0])
        else:
            date_range_result = None

        return ComputeEMAResponse(
            ticker=ticker,
            period=request.period,
            price_field=request.price_field,
            values=converged_values,
            candle_count=len(candles),
            ema_count=len(converged_values),
            date_range=date_range_result,
            coverage_warning=coverage_warning,
        )
