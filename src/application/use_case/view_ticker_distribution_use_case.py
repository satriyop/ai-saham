"""
View ticker distribution — cache-only broker counterparty matrix.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.ports.broker_distribution_provider import BrokerDistributionProvider
from src.domain.value_objects.broker_distribution import BrokerDistributionSnapshot


@dataclass(frozen=True)
class ViewTickerDistributionRequest:
    ticker: str
    trading_date: date | None = None  # None = provider latest/today


@dataclass(frozen=True)
class ViewTickerDistributionResult:
    ticker: str
    as_of: date
    source: str
    snapshot: BrokerDistributionSnapshot

    @property
    def fetch_hint(self) -> str:
        return f"saham fetch market {self.ticker}"


class ViewTickerDistributionUseCase:
    """Read-only distribution snapshot for one ticker."""

    def __init__(
        self,
        provider: BrokerDistributionProvider,
        *,
        source: str = "broker_distribution_cache",
    ) -> None:
        self._provider = provider
        self._source = source

    def execute(
        self, request: ViewTickerDistributionRequest
    ) -> ViewTickerDistributionResult | None:
        ticker = request.ticker.upper()
        snapshot = self._provider.get_distribution(ticker, request.trading_date)
        if snapshot is None:
            return None
        return ViewTickerDistributionResult(
            ticker=ticker,
            as_of=snapshot.date,
            source=self._source,
            snapshot=snapshot,
        )
