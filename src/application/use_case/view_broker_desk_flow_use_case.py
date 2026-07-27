"""
View desk net-by-date series from broker_daily_flow.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.broker_desk_from_daily_flow import (
    DeskDayNet,
    aggregate_desk_by_date,
    classify_desk_type,
)
from src.domain.entities.broker_flow import BrokerType
from src.domain.ports.broker_data_repository import BrokerDataRepository

TRACKED_DESK_SCOPE_NOTE = "Tracked desk activity only (broker_daily_flow)"


@dataclass(frozen=True)
class ViewBrokerDeskFlowRequest:
    broker_code: str
    days: int = 10


@dataclass(frozen=True)
class ViewBrokerDeskFlowResult:
    broker_code: str
    broker_name: str
    broker_type: BrokerType
    days: tuple[DeskDayNet, ...]
    scope_note: str = TRACKED_DESK_SCOPE_NOTE


class ViewBrokerDeskFlowUseCase:
    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(self, request: ViewBrokerDeskFlowRequest) -> ViewBrokerDeskFlowResult | None:
        code = request.broker_code.upper()
        flows = self._repository.get_broker_daily_flows_by_code(code)
        if not flows:
            return None

        day_nets = aggregate_desk_by_date(flows)
        # last N distinct trading days
        day_nets = day_nets[-request.days :]
        name = flows[-1].broker_name or code
        return ViewBrokerDeskFlowResult(
            broker_code=code,
            broker_name=name,
            broker_type=classify_desk_type(code, self._foreign_broker_codes),
            days=day_nets,
        )
