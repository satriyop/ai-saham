"""
Shared composition root for stock-axis view ticker use cases.

CLI and future TUI should both construct deps from here so wiring stays one place.

Layer: Infrastructure (composition)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
