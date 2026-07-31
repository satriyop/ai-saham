"""
View desk session calendar from broker_daily_flow.

~1 month of sessions: top stock · desk net · buy/sell totals.
Tracked desk only — not market foreign total.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.services.broker_desk_from_daily_flow import (
    DeskCalendarDay,
    build_desk_calendar_days,
    classify_desk_type,
    desk_session_dates,
)
from src.domain.entities.broker_flow import BrokerType
from src.domain.ports.broker_data_repository import BrokerDataRepository

TRACKED_DESK_SCOPE_NOTE = (
    "Tracked desk activity only (broker_daily_flow) · day cells · not market foreign total"
)


@dataclass(frozen=True)
class ViewBrokerDeskCalendarRequest:
    broker_code: str
    max_sessions: int = 22  # ~1 month of sessions-with-data


@dataclass(frozen=True)
class ViewBrokerDeskCalendarResult:
    broker_code: str
    broker_name: str
    broker_type: BrokerType
    as_of: date
    days: tuple[DeskCalendarDay, ...]
    sessions_cached: int
    scope_note: str = TRACKED_DESK_SCOPE_NOTE


class ViewBrokerDeskCalendarUseCase:
    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(
        self, request: ViewBrokerDeskCalendarRequest
    ) -> ViewBrokerDeskCalendarResult | None:
        code = request.broker_code.upper()
        flows = self._repository.get_broker_daily_flows_by_code(code)
        if not flows:
            return None
        dates = desk_session_dates(flows)
        if not dates:
            return None
        days = build_desk_calendar_days(flows, max_sessions=request.max_sessions)
        name = flows[0].broker_name or code
        return ViewBrokerDeskCalendarResult(
            broker_code=code,
            broker_name=name,
            broker_type=classify_desk_type(code, self._foreign_broker_codes),
            as_of=dates[-1],
            days=days,
            sessions_cached=len(dates),
        )
