"""
Shared dependency bundle for stock-analysis CLI workflow factories.

Layer: Adapter

Consolidates the duplicated repository/provider/engine wiring that was
previously repeated across analyze_swing, screen_accum, trade_accum, and
backtest factory modules into a single typed composition bundle.

No global singleton. No service locator. No workflow/policy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.adapters.cli.risk_engine_helper import create_configured_risk_engine
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.composition.signal_engine_factory import create_signal_engine
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
)
from src.infrastructure.config.config_backed_market_context_provider import (
    ConfigBackedMarketContextProvider,
)
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
from src.infrastructure.persistence.sqlite_observation_risk_assessment_repository import (
    SQLiteObservationRiskAssessmentRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

if TYPE_CHECKING:
    from src.application.ports.rules_loader import RulesLoader
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.application.services.institutional_flow_config import (
        InstitutionalAccumulationConfig,
    )
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.signal_scoring_config import SignalScoringConfig
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.infrastructure.browser.stockbit_providers import StockbitProviders
    from src.infrastructure.config.config_backed_market_context_provider import (
        ConfigBackedMarketContextProvider,
    )
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )
    from src.infrastructure.persistence.sqlite_observation_risk_assessment_repository import (
        SQLiteObservationRiskAssessmentRepository,
    )


@dataclass(frozen=True)
class StockAnalysisWorkflowDependencies:
    """Typed bundle of shared stock-analysis dependency graph.

    Every field is either a concrete shared instance or a factory callable
    so callers can either consume the instance directly or create fresh
    instances (e.g. indicator registry, rules loader) per use-case invocation.
    """

    db_path: Path
    broker_repository: BrokerDataRepository
    market_repository: MarketDataRepository
    candidate_observations_repository: SQLiteCandidateObservationsRepository
    observation_risk_assessment_repository: SQLiteObservationRiskAssessmentRepository
    stockbit_providers: StockbitProviders
    rules_loader_factory: Callable[[], RulesLoader]
    indicator_registry_factory: Callable[..., IndicatorRegistry]
    ticker_profile_classifier_factory: Callable[..., TickerProfileClassifier]
    institutional_accumulation_config_factory: Callable[
        ..., InstitutionalAccumulationConfig
    ]
    sector_context_builder_factory: Callable[..., SectorContextEvidenceBuilder]
    company_quality_context_builder_factory: Callable[
        ..., CompanyQualityContextEvidenceBuilder
    ]
    create_risk_engine: Callable[[], RiskEngine]
    create_signal_engine: Callable[[], SignalEngine]
    create_market_context_provider: Callable[[], ConfigBackedMarketContextProvider]


def create_stock_analysis_workflow_dependencies(
    db_path: Path,
) -> StockAnalysisWorkflowDependencies:
    """Construct a full dependency bundle for stock-analysis workflows.

    Owns concrete construction of all repositories, providers, and engine
    factories. Config is loaded lazily inside the bound engine callables,
    not at import time.
    """
    broker_repo = SQLiteBrokerRepository(db_path)
    market_repo = SQLiteMarketRepository(db_path=db_path)
    observations_repo = SQLiteCandidateObservationsRepository(db_path)
    risk_assessment_repo = SQLiteObservationRiskAssessmentRepository(db_path)
    stockbit_providers = create_readonly_stockbit_providers(db_path)

    def _make_risk_engine() -> RiskEngine:
        return create_configured_risk_engine(db_path, with_enrichment=True)

    def _make_signal_engine() -> SignalEngine:
        return create_signal_engine(db_path=db_path, with_enrichment=True)

    def _make_market_context_provider() -> ConfigBackedMarketContextProvider:
        return ConfigBackedMarketContextProvider(
            market_repository=market_repo,
            broker_repository=broker_repo,
        )

    app_config = load_app_config()
    config_paths = app_config.config_paths

    def _create_ticker_profile_classifier(
        profile_path: str | Path | None = None,
        universes_path: str | Path | None = None,
    ) -> TickerProfileClassifier:
        return create_ticker_profile_classifier(
            profile_path=profile_path or config_paths.ticker_profile,
            universes_path=universes_path or config_paths.universes,
        )

    def _load_institutional_accumulation_config(
        path: str | Path | None = None,
    ) -> InstitutionalAccumulationConfig:
        return load_institutional_accumulation_config(
            path=path or config_paths.institutional_accumulation,
        )

    def _create_sector_context_evidence_builder(
        config_path: str | Path | None = None,
        universes_path: str | Path | None = None,
    ) -> SectorContextEvidenceBuilder:
        return create_sector_context_evidence_builder(
            config_path=config_path or config_paths.sector_context,
            universes_path=universes_path or config_paths.universes,
        )

    def _create_company_quality_context_evidence_builder(
        config_path: str | Path | None = None,
        scoring: SignalScoringConfig | None = None,
        neutral_score: float = 50.0,
    ) -> CompanyQualityContextEvidenceBuilder:
        return create_company_quality_context_evidence_builder(
            config_path=config_path or config_paths.company_quality_context,
            scoring=scoring,
            neutral_score=neutral_score,
        )

    return StockAnalysisWorkflowDependencies(
        db_path=db_path,
        broker_repository=broker_repo,
        market_repository=market_repo,
        candidate_observations_repository=observations_repo,
        observation_risk_assessment_repository=risk_assessment_repo,
        stockbit_providers=stockbit_providers,
        rules_loader_factory=RulesYamlLoader,
        indicator_registry_factory=create_indicator_registry,
        ticker_profile_classifier_factory=_create_ticker_profile_classifier,
        institutional_accumulation_config_factory=(
            _load_institutional_accumulation_config
        ),
        sector_context_builder_factory=_create_sector_context_evidence_builder,
        company_quality_context_builder_factory=(
            _create_company_quality_context_evidence_builder
        ),
        create_risk_engine=_make_risk_engine,
        create_signal_engine=_make_signal_engine,
        create_market_context_provider=_make_market_context_provider,
    )
