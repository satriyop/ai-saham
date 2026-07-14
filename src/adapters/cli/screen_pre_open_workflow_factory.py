"""
Factory for `saham screen pre-open` workflow wiring.

Owns concrete infrastructure construction (Stockbit market status,
repositories, indicator registry, ticker notation provider, browser
providers, and AI research) so the CLI command module stays a thin adapter.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.application.services.pre_open_run_guard import PreOpenRunGuard
from src.application.use_case.pre_open_screen_use_case import PreOpenScreenUseCase
from src.application.use_case.pre_open_workflow_use_case import PreOpenWorkflowUseCase
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.market_status import MarketStatus
from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider
from src.infrastructure.browser.stockbit_market_time import get_current_market_status
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
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
        api_client = create_stockbit_api_client(
            profile_dir=Path(cfg.storage.stockbit_profile_dir),
            headless=headless,
        )
        provider = PlaywrightStockbitProvider(api_client=api_client)
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
    notation_provider = StockbitTickerNotationProvider(api_client=None, db_path=resolved_db)

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
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen_use_case,
        market_repository=market_repository,
        broker_repository=broker_repository,
        registry=registry,
        evaluate_market_context=evaluate_market_context,
        rules_loader=RulesYamlLoader(),
    )

    return PreOpenCliWorkflow(
        workflow=workflow,
        market_repository=market_repository,
        broker_repository=broker_repository,
        ai_warnings=ai_warnings,
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
