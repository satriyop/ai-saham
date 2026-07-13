"""
Factory for saham screen accum workflow wiring.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.services.bootstrap import (
    _resolve_risk_gates,
)
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowUseCase,
)
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
)
from src.infrastructure.config.engine_config_loader import load_engine_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.sector_context_config_loader import (
    create_sector_context_evidence_builder,
)
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_watchlist_repository import (
    SQLiteWatchlistRepository,
)


@dataclass(frozen=True)
class AccumulationScreenWorkflow:
    use_case: AccumulationScreenUseCase
    broker_repository: BrokerDataRepository
    market_repository: MarketDataRepository


def create_accumulation_screen_workflow(
    *,
    db_path: Path,
    screener_config: AccumulationScreenerConfig,
    with_risk: bool = True,
    swing_config: Any | None = None,
) -> AccumulationScreenWorkflow:
    """Build accumulation screen workflow dependencies for reconciliation."""
    swing_setup_catalog = (
        build_swing_setup_catalog_config(swing_config)
        if swing_config is not None
        else None
    )
    broker_repo = SQLiteBrokerRepository(db_path)
    market_repo = SQLiteMarketRepository(db_path=db_path)
    observations_repo = SQLiteCandidateObservationsRepository(db_path)
    stockbit_providers = create_readonly_stockbit_providers(db_path)

    risk_use_case = None
    if with_risk:
        structural_gates, execution_gates = _resolve_risk_gates(
            load_engine_config(Path(APP_CFG.config_paths.risk_engine))
        )
        risk_use_case = AssessRiskUseCase(
            repository=market_repo,
            structural_gates=structural_gates,
            execution_gates=execution_gates,
        )

    use_case = create_accumulation_screen_use_case(
        broker_repository=broker_repo,
        market_repository=market_repo,
        indicator_registry=create_indicator_registry(),
        stockbit_providers=stockbit_providers,
        risk_use_case=risk_use_case,
        candidate_observations_repository=observations_repo,
        foreign_flow_score_policy=screener_config.foreign_flow_score_policy,
        derived_feature_policy=screener_config.derived_features,
        swing_setup_catalog=swing_setup_catalog,
        rules_loader=RulesYamlLoader(),
        ticker_profile_classifier_factory=create_ticker_profile_classifier,
        institutional_accumulation_config_factory=load_institutional_accumulation_config,
        sector_context_builder_factory=create_sector_context_evidence_builder,
        company_quality_context_builder_factory=create_company_quality_context_evidence_builder,
    )

    return AccumulationScreenWorkflow(
        use_case=use_case,
        broker_repository=broker_repo,
        market_repository=market_repo,
    )


def create_run_accumulation_screen_workflow_use_case(
    *,
    db_path: Path,
    screener_config: AccumulationScreenerConfig,
    swing_config: Any,
) -> RunAccumulationScreenWorkflowUseCase:
    """Build the accumulation screen workflow use case with all dependencies wired."""
    base = create_accumulation_screen_workflow(
        db_path=db_path,
        screener_config=screener_config,
        swing_config=swing_config,
    )

    return RunAccumulationScreenWorkflowUseCase(
        screen_use_case=base.use_case,
        broker_repository=base.broker_repository,
        market_repository=base.market_repository,
        swing_config=swing_config,
        accumulation_screener_config=screener_config,
        rules_loader=RulesYamlLoader(),
        indicator_registry_factory=create_indicator_registry,
        save_watchlist_use_case=SaveScreenWatchlistUseCase(
            SQLiteWatchlistRepository(db_path)
        ),
    )
