"""
Factory for saham screen accum workflow wiring.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.adapters.composition.accumulation_risk_workflow_factory import (
    create_accumulation_assess_risk_use_case,
)
from src.adapters.composition.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
    create_stock_analysis_workflow_dependencies,
)
from src.application.services.accumulation_screen_factory import (
    AccumulationScreenUseCaseBundle,
    create_accumulation_screen_use_case,
    create_accumulation_screen_use_case_bundle,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.build_live_signal_evidence_execution_context_use_case import (
    BuildLiveSignalEvidenceExecutionContextUseCase,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowUseCase,
)
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.market_context import MarketContext
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
)
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
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
    dependencies: StockAnalysisWorkflowDependencies | None = None,
) -> AccumulationScreenWorkflow:
    """Build accumulation screen workflow dependencies for reconciliation."""
    deps = dependencies or create_stock_analysis_workflow_dependencies(db_path)
    swing_setup_catalog = (
        build_swing_setup_catalog_config(swing_config) if swing_config is not None else None
    )

    risk_use_case = (
        create_accumulation_assess_risk_use_case(
            market_repository=deps.market_repository,
        )
        if with_risk
        else None
    )
    signal_engine = deps.create_signal_engine()

    use_case = create_accumulation_screen_use_case(
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
        indicator_registry=deps.indicator_registry_factory(),
        stockbit_providers=deps.stockbit_providers,
        risk_use_case=risk_use_case,
        signal_engine=signal_engine,
        candidate_observations_repository=deps.learning_artifact_repository,
        accum_score_policy=screener_config.accum_score_policy,
        derived_feature_policy=screener_config.derived_features,
        swing_setup_catalog=swing_setup_catalog,
        rules_loader=deps.rules_loader_factory(),
        ticker_profile_classifier_factory=deps.ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=(deps.institutional_accumulation_config_factory),
        sector_context_builder_factory=deps.sector_context_builder_factory,
        sector_macro_context_builder_factory=deps.sector_macro_context_builder_factory,
        company_quality_context_builder_factory=(deps.company_quality_context_builder_factory),
    )

    return AccumulationScreenWorkflow(
        use_case=use_case,
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
    )


def create_accumulation_screen_workflow_bundle(
    *,
    db_path: Path,
    screener_config: AccumulationScreenerConfig,
    with_risk: bool = True,
    swing_config: Any | None = None,
    dependencies: StockAnalysisWorkflowDependencies | None = None,
) -> AccumulationScreenUseCaseBundle:
    """Build the screen use case together with its canonical observation recorder.

    Only for explicit observation-generation callers (e.g. research signal backfill).
    Diagnostic/read-only workflows must use create_accumulation_screen_workflow()
    instead, which never constructs a recorder.
    """
    deps = dependencies or create_stock_analysis_workflow_dependencies(db_path)
    swing_setup_catalog = (
        build_swing_setup_catalog_config(swing_config) if swing_config is not None else None
    )

    risk_use_case = (
        create_accumulation_assess_risk_use_case(
            market_repository=deps.market_repository,
        )
        if with_risk
        else None
    )
    signal_engine = deps.create_signal_engine()

    return create_accumulation_screen_use_case_bundle(
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
        indicator_registry=deps.indicator_registry_factory(),
        stockbit_providers=deps.stockbit_providers,
        risk_use_case=risk_use_case,
        signal_engine=signal_engine,
        candidate_observations_repository=deps.learning_artifact_repository,
        accum_score_policy=screener_config.accum_score_policy,
        derived_feature_policy=screener_config.derived_features,
        swing_setup_catalog=swing_setup_catalog,
        rules_loader=deps.rules_loader_factory(),
        ticker_profile_classifier_factory=deps.ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=(deps.institutional_accumulation_config_factory),
        sector_context_builder_factory=deps.sector_context_builder_factory,
        sector_macro_context_builder_factory=deps.sector_macro_context_builder_factory,
        company_quality_context_builder_factory=(deps.company_quality_context_builder_factory),
    )


def create_live_signal_evidence_execution_context_use_case(
    market_repository: MarketDataRepository,
) -> BuildLiveSignalEvidenceExecutionContextUseCase:
    """Wire the shared live-screen execution-context use case.

    Wiring only — no coverage dates or availability policy are computed
    here. Both `saham screen accum` and `saham screen compare` must build
    this through this one helper so they resolve the effective session and
    the gap-free IHSG-backed coverage window identically.
    """
    return BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=EffectiveMarketSessionResolver(market_repository),
        context_builder=SignalEvidenceExecutionContextBuilder(
            trading_session_calendar_loader=lambda start, end: IHSGTradingSessionCalendarProvider(
                market_repository
            ).load(
                coverage_start=start,
                coverage_end=end,
            )
        ),
        market_data_repository=market_repository,
    )


def create_run_accumulation_screen_workflow_use_case(
    *,
    db_path: Path,
    screener_config: AccumulationScreenerConfig,
    swing_config: Any,
    dependencies: StockAnalysisWorkflowDependencies | None = None,
) -> RunAccumulationScreenWorkflowUseCase:
    """Build the accumulation screen workflow use case with all dependencies wired."""
    deps = dependencies or create_stock_analysis_workflow_dependencies(db_path)
    base = create_accumulation_screen_workflow(
        db_path=db_path,
        screener_config=screener_config,
        swing_config=swing_config,
        dependencies=deps,
    )

    def _evaluate_display_market_context(
        *,
        as_of_date: date,
        universe: str,
    ) -> MarketContext:
        # Local-first factory; display-only — workflow must not pass this into
        # AccumulationScreenRequest.market_context without B-MCE-policy.
        return evaluate_market_context(
            db_path=db_path,
            as_of_date=as_of_date,
            universe=universe,
        )

    return RunAccumulationScreenWorkflowUseCase(
        screen_use_case=base.use_case,
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
        swing_config=swing_config,
        accumulation_screener_config=screener_config,
        rules_loader=deps.rules_loader_factory(),
        indicator_registry_factory=deps.indicator_registry_factory,
        live_signal_evidence_context_use_case=(
            create_live_signal_evidence_execution_context_use_case(deps.market_repository)
        ),
        save_watchlist_use_case=SaveScreenWatchlistUseCase(SQLiteWatchlistRepository(db_path)),
        evaluate_market_context=_evaluate_display_market_context,
    )
