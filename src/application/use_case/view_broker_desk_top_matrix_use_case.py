"""
View multi-window top-5 net-buy matrix for a tracked broker desk.

Cell facts: ticker · desk×ticker buy streak · net · lot-weighted avg buy.
Windows default 1/3/5/10/20 sessions-with-data; partial when cache shorter.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.services.broker_desk_from_daily_flow import (
    DESK_TOP_MATRIX_LIMIT,
    DESK_TOP_MATRIX_WINDOWS,
    DeskTickerWindowCell,
    classify_desk_type,
    desk_session_dates,
    rank_desk_top_buy_matrix,
)
from src.domain.entities.broker_flow import BrokerType
from src.domain.ports.broker_data_repository import BrokerDataRepository

TRACKED_DESK_SCOPE_NOTE = "Tracked desk activity only (broker_daily_flow) · top net buy by window"


@dataclass(frozen=True)
class ViewBrokerDeskTopMatrixRequest:
    broker_code: str
    windows: tuple[int, ...] = DESK_TOP_MATRIX_WINDOWS
    limit: int = DESK_TOP_MATRIX_LIMIT


@dataclass(frozen=True)
class ViewBrokerDeskTopMatrixResult:
    broker_code: str
    broker_name: str
    as_of: date
    broker_type: BrokerType
    windows: tuple[int, ...]
    # window → ranked cells (length ≤ limit; may be empty)
    columns: dict[int, tuple[DeskTickerWindowCell, ...]]
    sessions_cached: int
    scope_note: str = TRACKED_DESK_SCOPE_NOTE

    @property
    def top_ticker_1s(self) -> str | None:
        """Desk top name on default 1s column (for v jump)."""
        cells = self.columns.get(1) or ()
        if not cells:
            # fallback: smallest window with rows
            for w in sorted(self.columns):
                col = self.columns[w]
                if col:
                    return col[0].ticker
            return None
        return cells[0].ticker


class ViewBrokerDeskTopMatrixUseCase:
    def __init__(
        self,
        repository: BrokerDataRepository,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._foreign_broker_codes = foreign_broker_codes

    def execute(
        self, request: ViewBrokerDeskTopMatrixRequest
    ) -> ViewBrokerDeskTopMatrixResult | None:
        code = request.broker_code.upper()
        all_flows = self._repository.get_broker_daily_flows_by_code(code)
        if not all_flows:
            return None

        dates = desk_session_dates(all_flows)
        if not dates:
            return None

        columns = rank_desk_top_buy_matrix(
            all_flows,
            windows=request.windows,
            limit=request.limit,
        )
        name = all_flows[0].broker_name or code
        wins = tuple(sorted({int(w) for w in request.windows}))
        return ViewBrokerDeskTopMatrixResult(
            broker_code=code,
            broker_name=name,
            as_of=dates[-1],
            broker_type=classify_desk_type(code, self._foreign_broker_codes),
            windows=wins,
            columns=columns,
            sessions_cached=len(dates),
        )
