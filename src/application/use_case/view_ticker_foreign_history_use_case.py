"""
View ticker foreign-history — cache-only foreign_flow_points series.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.services.ticker_dashboard_flow import (
    FOREIGN_FLOW_SOURCE_PREFERENCE,
    select_foreign_flow_points,
)
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class ViewTickerForeignHistoryRequest:
    ticker: str
    days: int = 30
    source: str = "auto"  # auto | stockbit | idx


@dataclass(frozen=True)
class ViewTickerForeignHistoryResult:
    ticker: str
    days: int
    requested_source: str
    resolved_source: str
    points: tuple[ForeignFlowPoint, ...]
    as_of: date | None

    @property
    def fetch_hint(self) -> str:
        return f"saham fetch broker-history {self.ticker}"


class ViewTickerForeignHistoryUseCase:
    """Read-only foreign net history for one ticker."""

    def __init__(self, repository: BrokerDataRepository) -> None:
        self._repository = repository

    def execute(
        self, request: ViewTickerForeignHistoryRequest
    ) -> ViewTickerForeignHistoryResult | None:
        ticker = request.ticker.upper()
        days = max(1, min(int(request.days), 365))
        requested = (request.source or "auto").lower()
        if requested not in {"auto", "stockbit", "idx"}:
            raise ValueError("source must be auto, stockbit, or idx")

        if requested == "auto":
            by_source = {
                source: self._repository.get_foreign_flow_points(ticker, source=source)
                for source in FOREIGN_FLOW_SOURCE_PREFERENCE
            }
            points, resolved = select_foreign_flow_points(by_source)
        else:
            points = self._repository.get_foreign_flow_points(ticker, source=requested)
            resolved = requested if points else None

        if not points or not resolved:
            return None

        windowed = tuple(points[-days:])
        as_of = windowed[-1].date if windowed else None
        return ViewTickerForeignHistoryResult(
            ticker=ticker,
            days=days,
            requested_source=requested,
            resolved_source=resolved,
            points=windowed,
            as_of=as_of,
        )
