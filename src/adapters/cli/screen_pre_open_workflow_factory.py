"""
Factory for `saham screen pre-open` workflow wiring.

Owns concrete infrastructure construction (Stockbit market status,
repositories, indicator registry, ticker notation provider, browser
providers, and AI research) so the CLI command module stays a thin adapter.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from src.adapters.cli.risk_engine_helper import create_configured_risk_engine
from src.application.services.pre_open_observation_persister import (
    PreOpenObservationPersister,
)
from src.application.services.pre_open_risk_inputs_builder import PreOpenRiskInputsBuilder
from src.application.services.pre_open_run_guard import PreOpenRunGuard
from src.application.services.pre_open_signal_cascade import PreOpenSignalInputsBuilder
from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.application.services.screen_assessment_pipeline import ScreenAssessmentPipeline
from src.application.services.screen_policy import ScreenPolicy
from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenSnapshotScreenResult,
    PreOpenWorkflowUseCase,
)
from src.application.use_case.record_pre_open_observations_use_case import (
    RecordPreOpenObservationsUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.market_status import MarketStatus
from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.browser.stockbit_market_time import get_current_market_status
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def stockbit_session_exists() -> bool:
    cfg = load_app_config()
    return Path(cfg.storage.stockbit_session_file).exists()


def resolve_pre_open_market_status() -> MarketStatus:
    """Current IDX market status from Stockbit if session available, else wall-clock."""
    return get_current_market_status()


@dataclass(frozen=True)
class PreOpenBrowserPlan:
    """Result of resolving how to source pre-open movers data."""

    provider: BrowserDataProvider | None
    autonomous: bool
    session_missing: bool


def resolve_pre_open_browser_plan(
    *,
    movers_raw: list | None,
    order_books_raw: dict | None,
    headless: bool,
) -> PreOpenBrowserPlan:
    """Resolve the browser data provider for a pre-open run.

    When --movers-json was supplied, wrap it in a manual provider. Otherwise
    prefer an autonomous Playwright session; if none exists, signal that a
    provider could not be resolved so the caller can print the browser plan.
    """
    if movers_raw is not None:
        provider = ManualBrowserDataProvider.from_json(movers_raw, order_books_raw)
        return PreOpenBrowserPlan(provider=provider, autonomous=False, session_missing=False)

    if playwright_available() and stockbit_session_exists():
        cfg = load_app_config()
        stockbit_config = load_stockbit_provider_config()
        api_client = create_stockbit_api_client(
            profile_dir=Path(cfg.storage.stockbit_profile_dir),
            headless=headless,
            stockbit_config=stockbit_config,
        )
        provider = PlaywrightStockbitProvider(
            api_client=api_client, stockbit_config=stockbit_config
        )
        return PreOpenBrowserPlan(provider=provider, autonomous=True, session_missing=False)

    session_missing = playwright_available() and not stockbit_session_exists()
    return PreOpenBrowserPlan(provider=None, autonomous=False, session_missing=session_missing)


def create_pre_open_ai_explainer(
    *,
    with_ai: bool,
    provider: str | None,
) -> tuple[Any | None, list[str]]:
    """Build the optional AI research explainer, collecting user-facing warnings."""
    if not with_ai:
        return None, []

    warnings: list[str] = []
    try:
        from src.application.services.ai_research import ClaudeTickerResearcher

        if provider and provider not in ("claude", None):
            warnings.append(
                "Warning: AI research only supports 'claude' provider. Falling back."
            )
        return ClaudeTickerResearcher(), warnings
    except Exception as e:
        warnings.append(f"Warning: Could not initialize AI research: {e}")
        return None, warnings


@dataclass(frozen=True)
class PreOpenCliWorkflow:
    workflow: PreOpenWorkflowUseCase
    market_repository: MarketDataRepository
    broker_repository: BrokerDataRepository
    ai_warnings: list[str] = field(default_factory=list)
    record_observations_use_case: RecordPreOpenObservationsUseCase | None = None


def _build_run_snapshot_screen(
    *,
    db_path: Path,
    market_repository: MarketDataRepository,
    broker_repository: BrokerDataRepository,
    registry: Any,
    ai_explainer: Any,
    notation_provider: Any,
):
    """Build the outside-window snapshot fallback for `PreOpenWorkflowUseCase`.

    Reuses the existing `SQLiteIEVRepository` (already populated by
    `saham fetch iev`) instead of a live browser fetch, running the saved
    movers through the same `PreOpenScreenUseCase` pipeline.
    """
    iev_repository = SQLiteIEVRepository(db_path)

    def _run(
        config: PreOpenScreenConfig, as_of_date: date
    ) -> PreOpenSnapshotScreenResult | None:
        candidate_dates = [d for d in iev_repository.get_snapshot_dates() if d <= as_of_date]
        if not candidate_dates:
            return None
        snapshot_date = max(candidate_dates)

        snapshots = iev_repository.get_ncp_snapshot(snapshot_date)
        if not snapshots:
            return None

        movers = [MoverData(ticker=s.ticker, iev=s.iev, iep=s.iep) for s in snapshots]
        snapshot_provider = ManualBrowserDataProvider(movers=movers)
        # No order book was captured alongside the snapshot; skip that step.
        snapshot_config = replace(config, fast_mode=True)

        screen_use_case = PreOpenScreenUseCase(
            browser=snapshot_provider,
            repository=market_repository,
            registry=registry,
            broker_repository=broker_repository,
            ai_explainer=ai_explainer,
            ticker_notation_provider=notation_provider,
        )
        response = screen_use_case.execute(
            PreOpenScreenRequest(config=snapshot_config, run_date=as_of_date)
        )
        return PreOpenSnapshotScreenResult(snapshot_date=snapshot_date, response=response)

    return _run


def create_pre_open_cli_workflow(
    *,
    resolved_db: Path,
    browser_provider: BrowserDataProvider,
    with_ai: bool,
    ai_provider: str | None,
) -> PreOpenCliWorkflow:
    """Wire repositories, registry, notation provider, and the workflow use case."""
    market_repository = SQLiteMarketRepository(db_path=resolved_db)
    broker_repository = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repository,
        market_repository=market_repository,
    )
    notation_provider = StockbitTickerNotationProvider(
        api_client=None, db_path=resolved_db, stockbit_config=load_stockbit_provider_config()
    )

    ai_explainer, ai_warnings = create_pre_open_ai_explainer(
        with_ai=with_ai, provider=ai_provider
    )

    screen_use_case = PreOpenScreenUseCase(
        browser=browser_provider,
        repository=market_repository,
        registry=registry,
        broker_repository=broker_repository,
        ai_explainer=ai_explainer,
        ticker_notation_provider=notation_provider,
    )
    run_snapshot_screen = _build_run_snapshot_screen(
        db_path=resolved_db,
        market_repository=market_repository,
        broker_repository=broker_repository,
        registry=registry,
        ai_explainer=ai_explainer,
        notation_provider=notation_provider,
    )
    risk_engine = create_configured_risk_engine(
        db_path=resolved_db,
        with_enrichment=True,
    )
    assessment_pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open(),
        risk_engine=risk_engine,
        risk_inputs_builder=PreOpenRiskInputsBuilder(),
        evaluate_market_context=evaluate_market_context,
    )
    signal_config = PreOpenSignalConfig()
    signal_builder = PreOpenSignalInputsBuilder(signal_config)
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

    iev_repo = SQLiteIEVRepository(resolved_db)
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen_use_case,
        market_repository=market_repository,
        broker_repository=broker_repository,
        evaluate_market_context=evaluate_market_context,
        risk_engine=risk_engine,
        assessment_pipeline=assessment_pipeline,
        signal_builder=signal_builder,
        run_snapshot_screen=run_snapshot_screen,
        iev_delta_provider=iev_repo,
    )
    observations_repo = SQLiteCandidateObservationsRepository(resolved_db)
    record_observations = RecordPreOpenObservationsUseCase(
        workflow_use_case=workflow,
        observation_persister=PreOpenObservationPersister(
            observations_repo, signal_config=signal_config
        ),
    )

    return PreOpenCliWorkflow(
        workflow=workflow,
        market_repository=market_repository,
        broker_repository=broker_repository,
        ai_warnings=ai_warnings,
        record_observations_use_case=record_observations,
    )


__all__ = [
    "PreOpenBrowserPlan",
    "PreOpenCliWorkflow",
    "PreOpenRunGuard",
    "create_pre_open_ai_explainer",
    "create_pre_open_cli_workflow",
    "playwright_available",
    "resolve_pre_open_browser_plan",
    "resolve_pre_open_market_status",
    "stockbit_session_exists",
]
