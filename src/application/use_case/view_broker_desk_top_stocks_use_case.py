"""
View top stocks for a tracked broker desk from broker_daily_flow.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.services.broker_desk_from_daily_flow import (
    DeskTickerNet,
    classify_desk_type,
    rank_tickers_for_desk,
)
from src.domain.entities.broker_flow import BrokerType
from src.domain.ports.broker_data_repository import BrokerDataRepository

TRACKED_DESK_SCOPE_NOTE = "Tracked desk activity only (broker_daily_flow)"


@dataclass(frozen=True)
class ViewBrokerDeskTopStocksRequest:
    broker_code: str
    target_date: date | None = None  # None = latest date with data for this code
    limit: int = 20


@dataclass(frozen=True)
class ViewBrokerDeskTopStocksResult:
    broker_code: str
    broker_name: str
    date: date
    broker_type: BrokerType
    top_buy_stocks: tuple[DeskTickerNet, ...]
    top_sell_stocks: tuple[DeskTickerNet, ...]
    scope_note: str = TRACKED_DESK_SCOPE_NOTE


class ViewBrokerDeskTopStocksUseCase:
    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(
        self, request: ViewBrokerDeskTopStocksRequest
    ) -> ViewBrokerDeskTopStocksResult | None:
        code = request.broker_code.upper()
        all_flows = self._repository.get_broker_daily_flows_by_code(code)
        if not all_flows:
            return None

        if request.target_date is not None:
            query_date = request.target_date
            day_flows = [f for f in all_flows if f.date == query_date]
        else:
            query_date = max(f.date for f in all_flows)
            day_flows = [f for f in all_flows if f.date == query_date]

        if not day_flows:
            return None

        buyers, sellers = rank_tickers_for_desk(day_flows, limit=request.limit)
        name = day_flows[0].broker_name or code
        return ViewBrokerDeskTopStocksResult(
            broker_code=code,
            broker_name=name,
            date=query_date,
            broker_type=classify_desk_type(code, self._foreign_broker_codes),
            top_buy_stocks=buyers,
            top_sell_stocks=sellers,
        )
