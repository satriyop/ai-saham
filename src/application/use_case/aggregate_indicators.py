"""
AggregateIndicators use case - unified retrieval of SMA, EMA, and RSI.

This use case orchestrates multiple indicator calculations and provides
a date-aligned view of all indicators for a ticker.

It composes existing use cases rather than duplicating calculation logic,
ensuring warm-up buffer handling and validation are reused.

Layer: Application
Depends on: Domain ports, Domain value objects, Other use cases
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.use_case.compute_ema import ComputeEMARequest, ComputeEMAUseCase
from src.application.use_case.compute_rsi import ComputeRSIRequest, ComputeRSIUseCase
from src.application.use_case.compute_sma import ComputeSMARequest, ComputeSMAUseCase
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


@dataclass
class AggregateIndicatorsRequest:
    """Request DTO for aggregating indicators."""

    ticker: str
    sma_period: int = 20
    ema_period: int = 20
    rsi_period: int = 14
    days: int = 365  # How many days of history to return


@dataclass
class AggregateIndicatorsResponse:
    """Response DTO containing aggregated indicator snapshots."""

    ticker: str
    sma_period: int
    ema_period: int
    rsi_period: int
    snapshots: list[IndicatorSnapshot]
    candle_count: int
    snapshot_count: int
    date_range: tuple[date, date] | None

    @property
    def has_values(self) -> bool:
        """Check if any snapshots were created."""
        return len(self.snapshots) > 0


class AggregateIndicatorsUseCase:
    """
    Use case for retrieving SMA, EMA, and RSI together for a ticker.

    This is a read-only aggregation use case that:
    1. Validates the request
    2. Executes SMA, EMA, RSI computations via child use cases
    3. Aligns results by date (intersection)
    4. Creates IndicatorSnapshot for each common date

    Each child use case handles its own warm-up buffer, ensuring
    converged values are returned.

    Flow:
    1. Validate ticker
    2. Create and execute child use cases
    3. Build date-indexed dictionaries for each indicator
    4. Find common dates (intersection)
    5. Create IndicatorSnapshot for each common date
    6. Return response with metadata
    """

    def __init__(self, repository: MarketDataRepository) -> None:
        """
        Initialize with repository dependency.

        Args:
            repository: MarketDataRepository for fetching cached candles
        """
        self._repository = repository

    def execute(
        self, request: AggregateIndicatorsRequest
    ) -> AggregateIndicatorsResponse:
        """
        Execute the aggregate indicators use case.

        Args:
            request: Contains ticker, periods, and days

        Returns:
            AggregateIndicatorsResponse with aligned indicator snapshots

        Raises:
            ValueError: If ticker invalid or periods invalid
        """
        # Validate input
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        if request.sma_period < 1:
            raise ValueError("SMA period must be at least 1")
        if request.ema_period < 1:
            raise ValueError("EMA period must be at least 1")
        if request.rsi_period < 1:
            raise ValueError("RSI period must be at least 1")

        # Create child use cases with same repository
        sma_use_case = ComputeSMAUseCase(self._repository)
        ema_use_case = ComputeEMAUseCase(self._repository)
        rsi_use_case = ComputeRSIUseCase(self._repository)

        # Execute child use cases
        sma_response = sma_use_case.execute(
            ComputeSMARequest(
                ticker=ticker,
                period=request.sma_period,
                price_field="close",
                days=request.days,
            )
        )

        ema_response = ema_use_case.execute(
            ComputeEMARequest(
                ticker=ticker,
                period=request.ema_period,
                price_field="close",
                days=request.days,
            )
        )

        rsi_response = rsi_use_case.execute(
            ComputeRSIRequest(
                ticker=ticker,
                period=request.rsi_period,
                days=request.days,
            )
        )

        # Build date-indexed dictionaries
        sma_by_date: dict[date, Decimal] = {d: v for d, v in sma_response.values}
        ema_by_date: dict[date, Decimal] = {d: v for d, v in ema_response.values}
        rsi_by_date: dict[date, Decimal] = {d: v for d, v in rsi_response.values}

        # Find common dates (intersection)
        common_dates = (
            set(sma_by_date.keys())
            & set(ema_by_date.keys())
            & set(rsi_by_date.keys())
        )

        # Create snapshots for common dates, sorted by date
        snapshots = [
            IndicatorSnapshot(
                date=d,
                sma=sma_by_date[d],
                ema=ema_by_date[d],
                rsi=rsi_by_date[d],
            )
            for d in sorted(common_dates)
        ]

        # Calculate date range from snapshots
        if snapshots:
            date_range = (snapshots[0].date, snapshots[-1].date)
        else:
            date_range = None

        # Use max candle count from child responses for metadata
        candle_count = max(
            sma_response.candle_count,
            ema_response.candle_count,
            rsi_response.candle_count,
        )

        return AggregateIndicatorsResponse(
            ticker=ticker,
            sma_period=request.sma_period,
            ema_period=request.ema_period,
            rsi_period=request.rsi_period,
            snapshots=snapshots,
            candle_count=candle_count,
            snapshot_count=len(snapshots),
            date_range=date_range,
        )
