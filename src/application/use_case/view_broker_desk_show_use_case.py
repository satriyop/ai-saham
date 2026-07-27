"""
Compact desk dashboard from broker_daily_flow.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.services.broker_desk_from_daily_flow import (
    DeskTickerNet,
    classify_desk_type,
    rank_tickers_for_desk,
)
from src.application.use_case.view_broker_desk_top_stocks_use_case import (
    TRACKED_DESK_SCOPE_NOTE,
)
from src.domain.entities.broker_flow import BrokerType
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class ViewBrokerDeskShowRequest:
    broker_code: str
    top_limit: int = 5


@dataclass(frozen=True)
class ViewBrokerDeskShowResult:
    broker_code: str
    broker_name: str
    broker_type: BrokerType
    as_of: date
    day_net_value: Decimal
    day_net_lot: int
    day_ticker_count: int
    top_buy_stocks: tuple[DeskTickerNet, ...]
    top_sell_stocks: tuple[DeskTickerNet, ...]
    scope_note: str = TRACKED_DESK_SCOPE_NOTE


class ViewBrokerDeskShowUseCase:
    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(self, request: ViewBrokerDeskShowRequest) -> ViewBrokerDeskShowResult | None:
        code = request.broker_code.upper()
        flows = self._repository.get_broker_daily_flows_by_code(code)
        if not flows:
            return None

        as_of = max(f.date for f in flows)
        day_flows = [f for f in flows if f.date == as_of]
        buyers, sellers = rank_tickers_for_desk(day_flows, limit=request.top_limit)
        name = day_flows[0].broker_name or code
        return ViewBrokerDeskShowResult(
            broker_code=code,
            broker_name=name,
            broker_type=classify_desk_type(code, self._foreign_broker_codes),
            as_of=as_of,
            day_net_value=sum((f.net_value for f in day_flows), Decimal("0")),
            day_net_lot=sum(f.net_lot for f in day_flows),
            day_ticker_count=len({f.ticker.upper() for f in day_flows}),
            top_buy_stocks=buyers,
            top_sell_stocks=sellers,
        )
