"""
View ticker ownership history — cache-only period series + latest deltas.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.ports.shareholding_provider import ShareholdingProvider
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

DEFAULT_LIMIT = 8
MAX_LIMIT = 8


@dataclass(frozen=True)
class ViewTickerOwnershipHistoryRequest:
    ticker: str
    limit: int = DEFAULT_LIMIT
    as_of_date: date | None = None


@dataclass(frozen=True)
class ViewTickerOwnershipHistoryResult:
    ticker: str
    as_of: date | None
    periods: tuple[ShareholdingComposition, ...]  # oldest -> newest
    institution_pct_change: float | None
    float_change: float | None
    top_holder_pct_change: float | None


class ViewTickerOwnershipHistoryUseCase:
    """Read-only ownership period history for one ticker, with latest-period deltas."""

    def __init__(self, provider: ShareholdingProvider) -> None:
        self._provider = provider

    def execute(
        self, request: ViewTickerOwnershipHistoryRequest
    ) -> ViewTickerOwnershipHistoryResult | None:
        ticker = request.ticker.upper()
        limit = max(1, min(int(request.limit), MAX_LIMIT))
        newest_first = self._provider.get_history(ticker, limit, as_of_date=request.as_of_date)
        if not newest_first:
            return None

        periods = tuple(reversed(newest_first))  # oldest -> newest
        latest = periods[-1]
        institution_change: float | None = None
        float_change: float | None = None
        top_holder_change: float | None = None
        if len(periods) >= 2:
            previous = periods[-2]
            institution_change = round(latest.institution_pct - previous.institution_pct, 2)
            float_change = round(latest.free_float_pct - previous.free_float_pct, 2)
            top_holder_change = round(latest.top_holder_pct - previous.top_holder_pct, 2)

        as_of = latest.report_date or (latest.fetched_at.date() if latest.fetched_at else None)
        return ViewTickerOwnershipHistoryResult(
            ticker=ticker,
            as_of=as_of,
            periods=periods,
            institution_pct_change=institution_change,
            float_change=float_change,
            top_holder_pct_change=top_holder_change,
        )
