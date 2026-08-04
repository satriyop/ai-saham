"""
Shared composition root for stock-axis view ticker use cases.

CLI and future TUI should both construct deps from here so wiring stays one place.

Layer: Infrastructure (composition)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
        SQLiteCorporateActionCalendarRepository,
    )

from src.application.ports.ticker_dashboard_source import TickerDashboardSource
from src.application.use_case.get_ticker_dashboard_use_case import GetTickerDashboardUseCase
from src.application.use_case.view_ticker_distribution_use_case import (
    ViewTickerDistributionUseCase,
)
from src.application.use_case.view_ticker_financials_use_case import (
    ViewTickerFinancialsUseCase,
)
from src.application.use_case.view_ticker_flow_use_case import ViewTickerFlowUseCase
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryUseCase,
)
from src.application.use_case.view_ticker_ownership_history_use_case import (
    ViewTickerOwnershipHistoryUseCase,
)
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.broker_distribution_provider import BrokerDistributionProvider
from src.domain.ports.financials_repository import FinancialsRepository


@dataclass(frozen=True)
class ViewTickerDeps:
    """Cache-only dependency bundle for stock view surfaces."""

    db_path: Path
    broker_repository: BrokerDataRepository
    distribution_provider: BrokerDistributionProvider
    financials_repository: FinancialsRepository
    foreign_broker_codes: frozenset[str]
    dashboard: GetTickerDashboardUseCase
    top_brokers: ViewTickerTopBrokersUseCase
    flow: ViewTickerFlowUseCase
    foreign_history: ViewTickerForeignHistoryUseCase
    distribution: ViewTickerDistributionUseCase
    financials: ViewTickerFinancialsUseCase


def build_view_ticker_deps(db_path: Path | str) -> ViewTickerDeps:
    """Construct cache-only view-ticker dependencies for one database path."""
    from src.application.services.candidate_evidence_data_loader import (
        CandidateEvidenceDataLoader,
    )
    from src.application.services.ticker_dashboard_sector_macro_loader import (
        TickerDashboardSectorMacroLoader,
    )
    from src.infrastructure.browser.stockbit_broker_distribution import (
        StockbitBrokerDistributionProvider,
    )
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.config.sector_context_config_loader import (
        create_sector_context_evidence_builder,
    )
    from src.infrastructure.config.sector_macro_context_config_loader import (
        create_sector_macro_context_evidence_builder,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
    from src.infrastructure.persistence.sqlite_company_financials_repository import (
        SQLiteCompanyFinancialsRepository,
    )
    from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
        SQLiteMacroCalendarRepository,
    )
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )
    from src.infrastructure.persistence.sqlite_ticker_dashboard_source import (
        SQLiteTickerDashboardSource,
    )

    resolved = Path(db_path)
    repo = SQLiteBrokerRepository(resolved)
    financials_repo = SQLiteCompanyFinancialsRepository(resolved)
    foreign = load_institutional_accumulation_config().foreign_broker_codes
    dist_provider = StockbitBrokerDistributionProvider(
        api_client=None,
        db_path=resolved,
        stockbit_config=load_stockbit_provider_config(),
    )
    market_repo = SQLiteMarketRepository(db_path=resolved)
    smc_loader = TickerDashboardSectorMacroLoader(
        data_loader=CandidateEvidenceDataLoader(
            market_repo,
            repo,
            macro_calendar_repository=SQLiteMacroCalendarRepository(resolved),
        ),
        sector_macro_context_builder_factory=create_sector_macro_context_evidence_builder,
        sector_context_builder_factory=create_sector_context_evidence_builder,
    )
    return ViewTickerDeps(
        db_path=resolved,
        broker_repository=repo,
        distribution_provider=dist_provider,
        financials_repository=financials_repo,
        foreign_broker_codes=foreign,
        dashboard=GetTickerDashboardUseCase(
            SQLiteTickerDashboardSource(resolved),
            sector_macro_context_loader=smc_loader,
        ),
        top_brokers=ViewTickerTopBrokersUseCase(repo, foreign_broker_codes=foreign),
        flow=ViewTickerFlowUseCase(repo),
        foreign_history=ViewTickerForeignHistoryUseCase(repo),
        distribution=ViewTickerDistributionUseCase(dist_provider),
        financials=ViewTickerFinancialsUseCase(financials_repo),
    )


def build_read_only_ticker_dashboard_use_case(
    db_path: Path | str,
) -> GetTickerDashboardUseCase:
    """Construct the shared dashboard path without schema initialization.

    This narrow composition is reserved for side-effect-free consumers such as
    the closed agent tool registry. It reuses the same source methods and
    application use case as CLI/TUI view ticker, but requires an existing DB and
    never creates or migrates cache tables.
    """
    from src.application.services.candidate_evidence_data_loader import (
        CandidateEvidenceDataLoader,
    )
    from src.application.services.ticker_dashboard_sector_macro_loader import (
        TickerDashboardSectorMacroLoader,
    )
    from src.infrastructure.config.sector_context_config_loader import (
        create_sector_context_evidence_builder,
    )
    from src.infrastructure.config.sector_macro_context_config_loader import (
        create_sector_macro_context_evidence_builder,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )
    from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
        SQLiteMacroCalendarRepository,
    )
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )
    from src.infrastructure.persistence.sqlite_ticker_dashboard_source import (
        SQLiteTickerDashboardSource,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker dashboard database is unavailable: {resolved}")
    market_repo = SQLiteMarketRepository(resolved, initialize_schema=False)
    broker_repo = SQLiteBrokerRepository(resolved, initialize_schema=False)
    smc_loader = TickerDashboardSectorMacroLoader(
        data_loader=CandidateEvidenceDataLoader(
            market_repo,
            broker_repo,
            macro_calendar_repository=SQLiteMacroCalendarRepository(
                resolved,
                initialize_schema=False,
            ),
        ),
        sector_macro_context_builder_factory=create_sector_macro_context_evidence_builder,
        sector_context_builder_factory=create_sector_context_evidence_builder,
    )
    return GetTickerDashboardUseCase(
        SQLiteTickerDashboardSource(resolved, initialize_schema=False),
        sector_macro_context_loader=smc_loader,
    )


@dataclass(frozen=True)
class TickerBrokerFlowDeps:
    """Cache-only deps for the stock-centric ticker broker-flow agent tool."""

    top_brokers: ViewTickerTopBrokersUseCase
    bandar_source: object  # application port TickerDashboardSource (get_bandar)


def build_read_only_ticker_broker_flow_deps(
    db_path: Path | str,
) -> TickerBrokerFlowDeps:
    """Construct top-brokers + bandar cache readers without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables. Does not open the Stockbit
    bandar browser/fetch provider path.
    """
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )
    from src.infrastructure.persistence.sqlite_ticker_dashboard_source import (
        SQLiteTickerDashboardSource,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker broker-flow database is unavailable: {resolved}")
    foreign = load_institutional_accumulation_config().foreign_broker_codes
    repo = SQLiteBrokerRepository(resolved, initialize_schema=False)
    return TickerBrokerFlowDeps(
        top_brokers=ViewTickerTopBrokersUseCase(repo, foreign_broker_codes=foreign),
        bandar_source=SQLiteTickerDashboardSource(resolved, initialize_schema=False),
    )


def build_read_only_ticker_desk_flow_history_service(
    db_path: Path | str,
):
    """Construct multi-session desk history service without schema initialization."""
    from src.application.services.ticker_desk_flow_history import (
        TickerDeskFlowHistoryService,
    )
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker desk-flow-history database is unavailable: {resolved}")
    foreign = load_institutional_accumulation_config().foreign_broker_codes
    repo = SQLiteBrokerRepository(resolved, initialize_schema=False)
    return TickerDeskFlowHistoryService(repo, foreign_broker_codes=foreign)


def build_read_only_ticker_foreign_history_use_case(
    db_path: Path | str,
) -> ViewTickerForeignHistoryUseCase:
    """Construct foreign-history use case without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables.
    """
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker foreign-history database is unavailable: {resolved}")
    repo = SQLiteBrokerRepository(resolved, initialize_schema=False)
    return ViewTickerForeignHistoryUseCase(repo)


def build_read_only_ticker_ownership_source(
    db_path: Path | str,
) -> TickerDashboardSource:
    """Construct the ownership cache reader without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables.
    """
    from src.infrastructure.persistence.sqlite_ticker_dashboard_source import (
        SQLiteTickerDashboardSource,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker ownership database is unavailable: {resolved}")
    return SQLiteTickerDashboardSource(resolved, initialize_schema=False)


def build_read_only_ticker_ownership_history_use_case(
    db_path: Path | str,
) -> ViewTickerOwnershipHistoryUseCase:
    """Construct the ownership-history use case without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables; never opens a live API client.
    """
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker ownership-history database is unavailable: {resolved}")
    provider = StockbitShareholdingProvider(
        api_client=None,
        db_path=resolved,
        connection_provider=StockbitSQLiteConnectionProvider(initialize_schema=False),
        stockbit_config=load_stockbit_provider_config(),
    )
    return ViewTickerOwnershipHistoryUseCase(provider)


def build_read_only_ticker_fundamentals_trend_use_case(
    db_path: Path | str,
):
    """Construct fundamentals-trend use case without schema initialization."""
    from src.application.use_case.view_ticker_fundamentals_trend_use_case import (
        ViewTickerFundamentalsTrendUseCase,
    )
    from src.infrastructure.persistence.sqlite_ticker_dashboard_source import (
        SQLiteTickerDashboardSource,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"ticker fundamentals-trend database is unavailable: {resolved}"
        )
    return ViewTickerFundamentalsTrendUseCase(
        SQLiteTickerDashboardSource(resolved, initialize_schema=False)
    )


def build_read_only_ticker_sector_context_use_case(
    db_path: Path | str,
):
    """Construct BuildTickerSectorContextUseCase without schema initialization."""
    from src.application.services.candidate_evidence_data_loader import (
        CandidateEvidenceDataLoader,
    )
    from src.application.use_case.build_ticker_sector_context_use_case import (
        BuildTickerSectorContextUseCase,
    )
    from src.infrastructure.config.sector_context_config_loader import (
        create_sector_context_evidence_builder,
    )
    from src.infrastructure.config.sector_macro_context_config_loader import (
        create_sector_macro_context_evidence_builder,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )
    from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
        SQLiteMacroCalendarRepository,
    )
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker sector-context database is unavailable: {resolved}")
    market_repo = SQLiteMarketRepository(resolved, initialize_schema=False)
    broker_repo = SQLiteBrokerRepository(resolved, initialize_schema=False)
    data_loader = CandidateEvidenceDataLoader(
        market_repo,
        broker_repo,
        macro_calendar_repository=SQLiteMacroCalendarRepository(
            resolved,
            initialize_schema=False,
        ),
    )
    return BuildTickerSectorContextUseCase(
        data_loader,
        sector_context_builder_factory=create_sector_context_evidence_builder,
        sector_macro_context_builder_factory=create_sector_macro_context_evidence_builder,
        market_repository=market_repo,
    )


def build_read_only_ticker_corp_action_source(
    db_path: Path | str,
) -> SQLiteCorporateActionCalendarRepository:
    """Construct the corporate-action calendar reader without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables.
    """
    from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
        SQLiteCorporateActionCalendarRepository,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"corporate action calendar database is unavailable: {resolved}")
    return SQLiteCorporateActionCalendarRepository(resolved, initialize_schema=False)


def build_read_only_preopen_iev_source(db_path: Path | str):
    """Construct the pre-open IEV/NCP cache reader without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables.
    """
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"pre-open IEV database is unavailable: {resolved}")
    return SQLiteIEVRepository(resolved, initialize_schema=False)


def build_read_only_ticker_insider_source(db_path: Path | str):
    """Construct the insider-activity cache reader without schema initialization.

    Reserved for side-effect-free agent tool registration. Requires an existing
    DB file; never creates or migrates tables; never opens a live API client
    (``api_client=None`` makes every read cache-only regardless of ``as_of_date``).
    """
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )

    resolved = Path(db_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ticker insider-activity database is unavailable: {resolved}")
    return StockbitInsiderActivityProvider(
        api_client=None,
        db_path=resolved,
        connection_provider=StockbitSQLiteConnectionProvider(initialize_schema=False),
        stockbit_config=load_stockbit_provider_config(),
    )
