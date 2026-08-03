"""
Shared composition for desk-axis broker view use cases.

Layer: Infrastructure (composition)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.services.agent_broker_desk_tool import BrokerDeskUseCases
from src.application.use_case.view_broker_desk_calendar_use_case import (
    ViewBrokerDeskCalendarUseCase,
)
from src.application.use_case.view_broker_desk_flow_use_case import ViewBrokerDeskFlowUseCase
from src.application.use_case.view_broker_desk_history_use_case import (
    ViewBrokerDeskHistoryUseCase,
)
from src.application.use_case.view_broker_desk_show_use_case import ViewBrokerDeskShowUseCase
from src.application.use_case.view_broker_desk_top_matrix_use_case import (
    ViewBrokerDeskTopMatrixUseCase,
)
from src.application.use_case.view_broker_desk_top_stocks_use_case import (
    ViewBrokerDeskTopStocksUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass(frozen=True)
class ViewBrokerDeps:
    """Cache-only dependency bundle for broker desk surfaces."""

    db_path: Path
    broker_repository: BrokerDataRepository
    foreign_broker_codes: frozenset[str]
    show: ViewBrokerDeskShowUseCase
    top_stocks: ViewBrokerDeskTopStocksUseCase
    top_matrix: ViewBrokerDeskTopMatrixUseCase
    flow: ViewBrokerDeskFlowUseCase
    calendar: ViewBrokerDeskCalendarUseCase
    history: ViewBrokerDeskHistoryUseCase


def build_view_broker_deps(db_path: Path | str) -> ViewBrokerDeps:
    """Construct cache-only broker desk dependencies (may initialize schema)."""
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

    resolved = Path(db_path)
    repo = SQLiteBrokerRepository(resolved)
    foreign = load_institutional_accumulation_config().foreign_broker_codes
    return ViewBrokerDeps(
        db_path=resolved,
        broker_repository=repo,
        foreign_broker_codes=foreign,
        show=ViewBrokerDeskShowUseCase(repo, foreign_broker_codes=foreign),
        top_stocks=ViewBrokerDeskTopStocksUseCase(repo, foreign_broker_codes=foreign),
        top_matrix=ViewBrokerDeskTopMatrixUseCase(repo, foreign_broker_codes=foreign),
        flow=ViewBrokerDeskFlowUseCase(repo, foreign_broker_codes=foreign),
        calendar=ViewBrokerDeskCalendarUseCase(repo, foreign_broker_codes=foreign),
        history=ViewBrokerDeskHistoryUseCase(repo, foreign_broker_codes=foreign),
    )


def build_read_only_broker_desk_use_cases(db_path: Path | str) -> BrokerDeskUseCases:
    """Construct ViewBrokerDesk* use cases without schema initialization.

    Reserved for side-effect-free consumers such as the closed agent tool
    registry. Requires an existing DB file and never creates or migrates tables.
    """
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"broker desk database is unavailable: {resolved}")
    repo = SQLiteBrokerRepository(resolved, initialize_schema=False)
    foreign = load_institutional_accumulation_config().foreign_broker_codes
    return BrokerDeskUseCases(
        show=ViewBrokerDeskShowUseCase(repo, foreign_broker_codes=foreign),
        top_stocks=ViewBrokerDeskTopStocksUseCase(repo, foreign_broker_codes=foreign),
        top_matrix=ViewBrokerDeskTopMatrixUseCase(repo, foreign_broker_codes=foreign),
        flow=ViewBrokerDeskFlowUseCase(repo, foreign_broker_codes=foreign),
        calendar=ViewBrokerDeskCalendarUseCase(repo, foreign_broker_codes=foreign),
        history=ViewBrokerDeskHistoryUseCase(repo, foreign_broker_codes=foreign),
    )
