"""
Shared composition root for `saham screen` discovery use cases.

CLI and future TUI Discover construct deps from here so wiring stays one place.

Layer: Adapter (composition / wiring only)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.adapters.cli.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow,
    create_run_accumulation_screen_workflow_use_case,
)
from src.adapters.cli.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
    create_stock_analysis_workflow_dependencies,
)
from src.application.use_case.compare_screen_watchlist_use_case import (
    CompareScreenWatchlistUseCase,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ListScreenWatchlistsUseCase,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowUseCase,
)
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.swing_config import load_swing_config
from src.infrastructure.persistence.sqlite_watchlist_repository import (
    SQLiteWatchlistRepository,
)


@dataclass(frozen=True)
class ScreenDeps:
    """Discovery dependency bundle for screen surfaces."""

    db_path: Path
    stock_dependencies: StockAnalysisWorkflowDependencies
    broker_repository: BrokerDataRepository
    market_repository: MarketDataRepository
    watchlist_repository: SQLiteWatchlistRepository
    list_watchlists: ListScreenWatchlistsUseCase
    save_watchlist: SaveScreenWatchlistUseCase
    screener_config: AccumulationScreenerConfig
    swing_config: Any

    def build_accum_workflow_use_case(self) -> RunAccumulationScreenWorkflowUseCase:
        return create_run_accumulation_screen_workflow_use_case(
            db_path=self.db_path,
            screener_config=self.screener_config,
            swing_config=self.swing_config,
            dependencies=self.stock_dependencies,
        )

    def build_accum_workflow(self, *, with_risk: bool = True):
        return create_accumulation_screen_workflow(
            db_path=self.db_path,
            screener_config=self.screener_config,
            with_risk=with_risk,
            swing_config=self.swing_config,
            dependencies=self.stock_dependencies,
        )

    def build_compare_watchlist_use_case(self) -> CompareScreenWatchlistUseCase:
        return CompareScreenWatchlistUseCase(
            watchlist_repository=self.watchlist_repository,
            screen_workflow_use_case=self.build_accum_workflow_use_case(),
        )


def build_screen_deps(db_path: Path | str | None = None) -> ScreenDeps:
    """Construct screen discovery dependencies for one database path."""
    cfg = load_app_config()
    resolved = Path(db_path) if db_path is not None else Path(cfg.storage.db_path)
    stock_deps = create_stock_analysis_workflow_dependencies(resolved)
    watchlist_repo = SQLiteWatchlistRepository(resolved)
    return ScreenDeps(
        db_path=resolved,
        stock_dependencies=stock_deps,
        broker_repository=stock_deps.broker_repository,
        market_repository=stock_deps.market_repository,
        watchlist_repository=watchlist_repo,
        list_watchlists=ListScreenWatchlistsUseCase(watchlist_repo),
        save_watchlist=SaveScreenWatchlistUseCase(watchlist_repo),
        screener_config=load_accumulation_screener_config(
            Path(cfg.config_paths.accumulation_screener)
        ),
        swing_config=load_swing_config(),
    )
