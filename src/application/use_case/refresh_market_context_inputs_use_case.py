"""
Refresh MarketContextEngine global context ticker inputs use case.

Loops through pre-resolved global context ticker inputs (^VIX, EIDO, IDR=X,
etc.) and refreshes each via an injected callable. Ticker resolution
(which factors are enabled, tolerance days) and the underlying
provider/repository construction are the caller's responsibility — this
use case is pure orchestration: no config loading, no provider or
repository construction, no infrastructure imports.

Layer: Application
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class GlobalContextTickerInput:
    """One resolved global context ticker to refresh."""

    ticker: str
    factor: str
    end_tolerance_days: int


@dataclass(frozen=True)
class RefreshMarketContextInputsRequest:
    """Request DTO for refreshing MCE global context ticker inputs."""

    tickers: tuple[GlobalContextTickerInput, ...]
    days: int
    refresh_ticker: Callable[[str, int, int], str]


@dataclass(frozen=True)
class RefreshMarketContextInputsResponse:
    """Response DTO carrying one status string per fetched global context ticker."""

    statuses: tuple[str, ...]


class RefreshMarketContextInputsUseCase:
    """Refresh candle cache for pre-resolved MCE global context tickers."""

    def execute(
        self, request: RefreshMarketContextInputsRequest
    ) -> RefreshMarketContextInputsResponse:
        results: list[str] = []
        for ticker_input in request.tickers:
            try:
                status = request.refresh_ticker(
                    ticker_input.ticker,
                    request.days,
                    ticker_input.end_tolerance_days,
                )
                if status.startswith("cached"):
                    status = "✓"
                results.append(f"{ticker_input.ticker}({ticker_input.factor}):{status}")
            except Exception as e:
                results.append(
                    f"{ticker_input.ticker}({ticker_input.factor}):ERR:{str(e)[:20]}"
                )

        return RefreshMarketContextInputsResponse(statuses=tuple(results))
