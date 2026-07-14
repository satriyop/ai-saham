"""
Dependency wiring for the `saham trade confirm` CLI command.

Layer: Adapter

This module is allowed to import infrastructure directly; it is the
composition point for RunIntradayConfirmationWorkflowUseCase. Stockbit
session/provider construction is wired as a lazy callable — it only runs
when the use case determines live auto-resolution is actually needed, so a
fully-manual or track-file-backed confirmation never touches Stockbit.
Imports of the concrete Stockbit modules stay inside that callable (not at
module import time) so tests can monkeypatch the underlying infrastructure
modules.
"""

from __future__ import annotations

from typing import Any, Callable

from src.application.use_case.run_intraday_confirmation_workflow_use_case import (
    RunIntradayConfirmationWorkflowUseCase,
)
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config


class IntradayAutoConfirmSetupError(RuntimeError):
    """Raised when constructing live Stockbit providers fails unexpectedly."""


def _build_live_providers():
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.browser.stockbit_order_book import (
        StockbitOrderBookProvider,
    )
    from src.infrastructure.browser.stockbit_running_trade import (
        StockbitRunningTradeProvider,
    )
    from src.infrastructure.composition.stockbit_session_factory import (
        get_stockbit_session,
    )

    try:
        stockbit_config = load_stockbit_provider_config()
        session = get_stockbit_session(stockbit_config)
        if session is None or not session.authenticated:
            return None, None
        api = session.api_client
        return (
            StockbitRunningTradeProvider(api_client=api, stockbit_config=stockbit_config),
            StockbitOrderBookProvider(api_client=api, stockbit_config=stockbit_config),
        )
    except Exception as e:
        raise IntradayAutoConfirmSetupError(str(e)) from e


def create_run_intraday_confirmation_workflow(
    *,
    live_auto_resolution_enabled: bool,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> RunIntradayConfirmationWorkflowUseCase:
    pre_open_config = load_pre_open_screen_config()

    provider_factory = _build_live_providers if live_auto_resolution_enabled else None

    return RunIntradayConfirmationWorkflowUseCase(
        provider_factory=provider_factory,
        pre_open_config=pre_open_config,
        on_event=on_event,
    )
