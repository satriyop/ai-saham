"""
View desk history rows from broker_daily_flow (optional ticker pin).

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.broker_desk_from_daily_flow import classify_desk_type
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerType
from src.domain.ports.broker_data_repository import BrokerDataRepository

TRACKED_DESK_SCOPE_NOTE = "Tracked desk activity only (broker_daily_flow)"


@dataclass(frozen=True)
class ViewBrokerDeskHistoryRequest:
    broker_code: str
    days: int = 30
    ticker: str | None = None


@dataclass(frozen=True)
class ViewBrokerDeskHistoryResult:
    broker_code: str
    broker_name: str
    broker_type: BrokerType
    flows: tuple[BrokerDailyFlow, ...]
    pinned_ticker: str | None
    scope_note: str = TRACKED_DESK_SCOPE_NOTE


class ViewBrokerDeskHistoryUseCase:
    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(self, request: ViewBrokerDeskHistoryRequest) -> ViewBrokerDeskHistoryResult | None:
        code = request.broker_code.upper()
        pin = request.ticker.upper() if request.ticker else None
        flows = self._repository.get_broker_daily_flows_by_code(code, ticker=pin)
        if not flows:
            return None

        # Keep last N distinct dates, then all rows on those dates
        dates = sorted({f.date for f in flows})
        keep_dates = set(dates[-request.days :])
        window = tuple(f for f in flows if f.date in keep_dates)
        name = window[0].broker_name or code
        return ViewBrokerDeskHistoryResult(
            broker_code=code,
            broker_name=name,
            broker_type=classify_desk_type(code, self._foreign_broker_codes),
            flows=window,
            pinned_ticker=pin,
        )
