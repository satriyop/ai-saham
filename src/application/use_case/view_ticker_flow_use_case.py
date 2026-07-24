"""
View ticker flow — multi-day foreign flow from broker_summaries.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.domain.entities.broker_flow import BrokerSummary
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class ViewTickerFlowRequest:
    ticker: str
    days: int = 10
    as_of: date | None = None  # None = today (calendar end for range)


@dataclass(frozen=True)
class ViewTickerFlowResult:
    ticker: str
    days: int
    source: str
    summaries: tuple[BrokerSummary, ...]
    as_of: date | None
    total_net_value: Decimal
    buy_days: int
    sell_days: int

    @property
    def fetch_hint(self) -> str:
        return f"saham fetch market {self.ticker}"


class ViewTickerFlowUseCase:
    """Read-only foreign flow summary table for one ticker."""

    def __init__(self, repository: BrokerDataRepository) -> None:
        self._repository = repository

    def execute(self, request: ViewTickerFlowRequest) -> ViewTickerFlowResult | None:
        ticker = request.ticker.upper()
        days = max(1, min(int(request.days), 365))
        end_date = request.as_of or date.today()
        # Weekend/holiday buffer so N trading days can be filled.
        start_date = end_date - timedelta(days=days + 10)

        summaries = self._repository.get_broker_summaries(
            ticker, start_date=start_date, end_date=end_date
        )
        if not summaries:
            return None

        windowed = tuple(summaries[-days:])
        if not windowed:
            return None

        total_net = sum((s.foreign_net_value for s in windowed), Decimal("0"))
        buy_days = sum(1 for s in windowed if s.is_foreign_accumulating)
        sell_days = len(windowed) - buy_days
        # Prefer last summary's source label when homogeneous; else mixed marker.
        sources = {s.source for s in windowed if s.source}
        source = next(iter(sources)) if len(sources) == 1 else "mixed"

        return ViewTickerFlowResult(
            ticker=ticker,
            days=days,
            source=source,
            summaries=windowed,
            as_of=windowed[-1].date,
            total_net_value=total_net,
            buy_days=buy_days,
            sell_days=sell_days,
        )
