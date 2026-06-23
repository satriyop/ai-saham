"""
ComputeRSI use case - orchestrates RSI calculation with warm-up buffer handling.

This use case coordinates between:
- MarketDataRepository (retrieves cached candles)
- RSI indicator (pure calculation)

It implements a read-only analysis pattern with professional-grade
warm-up buffer handling to ensure converged RSI values.

Layer: Application
Depends on: Domain ports, Domain indicators
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.domain.indicators.rsi import calculate_rsi
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass
class ComputeRSIRequest:
    """Request DTO for computing RSI."""

    ticker: str
    period: int = 14  # Industry standard RSI period
    days: int = 365  # How many days of history to return


_COVERAGE_TOLERANCE_DAYS = 7  # acceptable shortfall before emitting a warning


@dataclass
class ComputeRSIResponse:
    """Response DTO containing RSI calculation results."""

    ticker: str
    period: int
    values: list[tuple[date, Decimal]]
    candle_count: int
    rsi_count: int
    date_range: tuple[date, date] | None
    coverage_warning: str | None = None

    @property
    def has_values(self) -> bool:
        """Check if any RSI values were calculated."""
        return len(self.values) > 0


class ComputeRSIUseCase:
    """
    Use case for computing RSI over cached market data.

    Implements professional-grade warm-up buffer handling:
    1. Over-fetches candles by 3× period (warm-up buffer)
    2. Calculates RSI over full dataset
    3. Slices off warm-up region
    4. Returns only converged values within user's requested window

    RSI uses Wilder's smoothing which has a slower decay than standard EMA,
    requiring a longer warm-up period (3× vs EMA's 2×) for convergence.

    Flow:
    1. Validate request
    2. Over-fetch candles (requested days + warm-up buffer)
    3. Calculate RSI using domain indicator
    4. Slice off warm-up region
    5. Return converged results with metadata
    """

    # RSI uses Wilder's smoothing (slower decay), needs longer warm-up
    WARM_UP_MULTIPLIER = 3

    def __init__(self, repository: MarketDataRepository) -> None:
        """
        Initialize with repository dependency.

        Args:
            repository: MarketDataRepository for fetching cached candles
        """
        self._repository = repository

    def execute(self, request: ComputeRSIRequest) -> ComputeRSIResponse:
        """
        Execute the compute RSI use case.

        Args:
            request: Contains ticker, period, days

        Returns:
            ComputeRSIResponse with RSI values and metadata

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
            return ComputeRSIResponse(
                ticker=ticker,
                period=request.period,
                values=[],
                candle_count=0,
                rsi_count=0,
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

        # Calculate warm-up buffer (3× period for RSI convergence)
        warm_up_days = request.period * self.WARM_UP_MULTIPLIER

        # Calculate how far back we need to go, but don't go beyond available data
        total_days_needed = min(request.days + warm_up_days, (latest_date - earliest_date).days + 1)
        fetch_start_date = latest_date - timedelta(days=total_days_needed - 1)

        # User cutoff: after excluding warm-up buffer
        user_cutoff_date = latest_date - timedelta(days=request.days - 1)

        # Fetch candles from cache (over-fetched to include warm-up region)
        candles = self._repository.get_candles(ticker, fetch_start_date, latest_date)

        # Handle no data case
        if not candles:
            return ComputeRSIResponse(
                ticker=ticker,
                period=request.period,
                values=[],
                candle_count=0,
                rsi_count=0,
                date_range=None,
            )

        # Calculate RSI using domain indicator (includes warm-up region)
        full_rsi_values = calculate_rsi(candles, period=request.period)

        # Slice off warm-up region: keep only values >= user_cutoff_date
        converged_values = [(d, v) for d, v in full_rsi_values if d >= user_cutoff_date]

        # Calculate date range of returned values
        if converged_values:
            date_range_result = (converged_values[0][0], converged_values[-1][0])
        else:
            date_range_result = None

        return ComputeRSIResponse(
            ticker=ticker,
            period=request.period,
            values=converged_values,
            candle_count=len(candles),
            rsi_count=len(converged_values),
            date_range=date_range_result,
            coverage_warning=coverage_warning,
        )
