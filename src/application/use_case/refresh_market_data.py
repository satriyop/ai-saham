"""
Refresh market data use case.

Owns deterministic candle refresh policy:
- cache coverage checks
- older backfill vs forward-fill decisions
- forced refresh behavior
- persisted-row status metadata

Layer: Application
"""

from dataclasses import dataclass
from datetime import date, timedelta

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import MarketDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository

DEFAULT_START_TOLERANCE_DAYS = 7
DEFAULT_END_TOLERANCE_DAYS = 7


@dataclass(frozen=True)
class RefreshMarketDataRequest:
    """Request DTO for refreshing locally persisted OHLCV candles."""

    ticker: str
    days: int
    refresh: bool = False
    end_date: date | None = None
    start_tolerance_days: int = DEFAULT_START_TOLERANCE_DAYS
    end_tolerance_days: int = DEFAULT_END_TOLERANCE_DAYS


@dataclass(frozen=True)
class RefreshMarketDataResponse:
    """Response DTO for market data refresh results."""

    ticker: str
    status: str
    candles: list[Candle]
    date_range: tuple[date, date] | None
    added_count: int
    fetch_modes: frozenset[str]
    short_history_note: str | None = None

    @property
    def count(self) -> int:
        return len(self.candles)


class RefreshMarketDataUseCase:
    """Refresh OHLCV candles with cache-aware backfill and forward-fill."""

    def __init__(
        self,
        provider: MarketDataProvider,
        repository: MarketDataRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def execute(self, request: RefreshMarketDataRequest) -> RefreshMarketDataResponse:
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")
        if request.days < 1:
            raise ValueError("Days must be at least 1")

        end_date = request.end_date or date.today()
        requested_start = end_date - timedelta(days=request.days)
        previous_latest: date | None = None
        fetch_ranges: list[tuple[date, date, str]] = []
        short_history_note: str | None = None

        if not request.refresh:
            existing = self._repository.get_date_range(ticker)
            if existing:
                earliest, latest = existing
                previous_latest = latest
                tolerated_start = requested_start + timedelta(
                    days=request.start_tolerance_days
                )
                tolerated_end = end_date - timedelta(days=request.end_tolerance_days)
                needs_older_backfill = earliest > tolerated_start
                needs_forward_fill = latest < tolerated_end

                if needs_older_backfill:
                    cached_days = (latest - earliest).days
                    short_history_note = (
                        f"  candles {ticker}: {cached_days}d cached "
                        f"(from {earliest}), requested {request.days}d "
                        "- backfilling older gap"
                    )
                    fetch_ranges.append((
                        requested_start,
                        earliest - timedelta(days=1),
                        "backfill",
                    ))

                if needs_forward_fill:
                    fetch_ranges.append((latest + timedelta(days=1), end_date, "forward"))

                if not fetch_ranges:
                    candles = self._repository.get_candles(
                        ticker, requested_start, end_date
                    )
                    return RefreshMarketDataResponse(
                        ticker=ticker,
                        status="cached-current",
                        candles=candles,
                        date_range=self._date_range(candles),
                        added_count=0,
                        fetch_modes=frozenset(),
                    )
            else:
                fetch_ranges.append((requested_start, end_date, "initial"))
        else:
            fetch_ranges.append((requested_start, end_date, "refresh"))

        before_dates = {c.date for c in self._repository.get_candles(ticker)}
        fetch_modes: set[str] = set()

        for start_date, fetch_end_date, fetch_mode in fetch_ranges:
            if start_date > fetch_end_date:
                continue
            fetch_modes.add(fetch_mode)
            candles = self._provider.fetch_daily_ohlcv(ticker, start_date, fetch_end_date)
            if candles:
                self._repository.save_candles(candles)

        after_dates = {c.date for c in self._repository.get_candles(ticker)}
        added_count = len(after_dates - before_dates)

        if previous_latest is not None and added_count == 0:
            status = f"up-to-date({previous_latest.isoformat()})"
        else:
            status = self._range_update_status(
                added_count=added_count,
                updated_range=self._repository.get_date_range(ticker),
                fetch_modes=fetch_modes,
            )

        candles = self._repository.get_candles(ticker, requested_start, end_date)
        return RefreshMarketDataResponse(
            ticker=ticker,
            status=status,
            candles=candles,
            date_range=self._date_range(candles),
            added_count=added_count,
            fetch_modes=frozenset(fetch_modes),
            short_history_note=short_history_note,
        )

    def _range_update_status(
        self,
        added_count: int,
        updated_range: tuple[date, date] | None,
        fetch_modes: set[str],
    ) -> str:
        if added_count == 0 and updated_range is None:
            return "no-data"

        span_days = (
            (updated_range[1] - updated_range[0]).days + 1
            if updated_range
            else 0
        )
        prefix = "backfill+" if "backfill" in fetch_modes else "+"
        return f"{prefix}{added_count}rows/span={span_days}d"

    def _date_range(self, candles: list[Candle]) -> tuple[date, date] | None:
        if not candles:
            return None
        return candles[0].date, candles[-1].date
