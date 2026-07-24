"""
View broker top buyers/sellers from cached data only.

Prefers market top lists on ``broker_summaries``. When those lists are empty
(common for IDX-sourced summaries), falls back to ranking
``broker_daily_flow`` for the same date and labels the scope as tracked
brokers only.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.services.broker_top_from_daily_flow import (
    TRACKED_TOPS_NOTE,
    TRACKED_TOPS_SCOPE,
    TRACKED_TOPS_SOURCE,
    rank_top_brokers_from_daily_flows,
)
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class ViewBrokerTopRequest:
    ticker: str
    target_date: date | None = None  # None = latest summary date
    limit: int = 10


@dataclass(frozen=True)
class ViewBrokerTopResult:
    """Resolved top-broker view for one ticker/date."""

    ticker: str
    date: date
    summary: BrokerSummary
    top_buyers: tuple[BrokerTransaction, ...]
    top_sellers: tuple[BrokerTransaction, ...]
    # "summary" = broker_summaries.top_*; "broker_daily_flow" = tracked fallback
    tops_source: str
    tops_scope: str | None  # "tracked_brokers" when fallback; None for full summary tops
    tops_scope_note: str | None


class ViewBrokerTopUseCase:
    """Read-only use case: summary tops with optional tracked-flow fallback."""

    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        """
        Args:
            repository: Cached broker data repository.
            foreign_broker_codes: Config set used to classify Type on daily-flow
                fallback (FOREIGN if code in set, else LOCAL). None leaves type
                UNKNOWN. Summary tops keep their stored type unchanged.
        """
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(self, request: ViewBrokerTopRequest) -> ViewBrokerTopResult | None:
        ticker = request.ticker.upper()
        summary = self._resolve_summary(ticker, request.target_date)
        if summary is None:
            return None

        if summary.top_buyers or summary.top_sellers:
            return ViewBrokerTopResult(
                ticker=ticker,
                date=summary.date,
                summary=summary,
                top_buyers=summary.top_buyers[: request.limit],
                top_sellers=summary.top_sellers[: request.limit],
                tops_source="summary",
                tops_scope=None,
                tops_scope_note=None,
            )

        flows = self._repository.get_broker_daily_flows(
            ticker,
            start_date=summary.date,
            end_date=summary.date,
        )
        buyers, sellers = rank_top_brokers_from_daily_flows(
            flows,
            limit=request.limit,
            foreign_broker_codes=self._foreign_broker_codes,
        )
        if not buyers and not sellers:
            # Summary exists but no tops and no tracked rows for that date.
            return ViewBrokerTopResult(
                ticker=ticker,
                date=summary.date,
                summary=summary,
                top_buyers=(),
                top_sellers=(),
                tops_source="summary",
                tops_scope=None,
                tops_scope_note=None,
            )

        return ViewBrokerTopResult(
            ticker=ticker,
            date=summary.date,
            summary=summary,
            top_buyers=buyers,
            top_sellers=sellers,
            tops_source=TRACKED_TOPS_SOURCE,
            tops_scope=TRACKED_TOPS_SCOPE,
            tops_scope_note=TRACKED_TOPS_NOTE,
        )

    def _resolve_summary(
        self,
        ticker: str,
        target_date: date | None,
    ) -> BrokerSummary | None:
        if target_date is not None:
            return self._repository.get_broker_summary(ticker, target_date)

        summaries = self._repository.get_broker_summaries(ticker)
        if not summaries:
            return None
        return summaries[-1]
