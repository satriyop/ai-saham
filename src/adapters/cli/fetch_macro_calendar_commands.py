"""
CLI command for the market-wide macroeconomic calendar sync.

`saham fetch macro-calendar` — fetches Stockbit `/corpaction/economic`, stores
normalized events, reports per-category counts. Thin adapter: parse input,
wire dependencies, one use-case call, format output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.sync_macro_calendar_use_case import (
    SyncMacroCalendarRequest,
    SyncMacroCalendarUseCase,
)
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.browser.stockbit_macro_calendar import StockbitMacroCalendarProvider
from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
    SQLiteMacroCalendarRepository,
)


def fetch_macro_calendar(
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Force remote fetch, bypass sync marker"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Sync the macroeconomic calendar from Stockbit (BI rate, CPI, etc.).

    Distinct from `saham fetch calendar` (corporate actions). Events are stored
    in macro_calendar_events for rates/P2 consumers — not CA risk.

    Requires an active Stockbit session (run 'saham fetch stockbit login').

    Examples:
        saham fetch macro-calendar
        saham fetch macro-calendar --refresh
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    stockbit_config = load_stockbit_provider_config()
    session = get_stockbit_session(stockbit_config)
    if session is None or not session.authenticated:
        typer.echo(
            typer.style("Not authenticated.", fg=typer.colors.RED)
            + " Run: saham fetch stockbit login",
            err=True,
        )
        raise typer.Exit(1)

    provider = StockbitMacroCalendarProvider(
        api_client=session.api_client, stockbit_config=stockbit_config
    )
    repository = SQLiteMacroCalendarRepository(resolved_db)
    use_case = SyncMacroCalendarUseCase(provider=provider, repository=repository)

    response = use_case.execute(
        SyncMacroCalendarRequest(
            sync_date=date.today(),
            force_remote_fetch=refresh,
        )
    )

    if response.from_cache:
        typer.echo("Already synced today — use --refresh to force.")
        return

    if response.status == "failed":
        typer.echo(typer.style("Macro calendar sync failed.", fg=typer.colors.RED), err=True)
        for err in response.errors:
            typer.echo(typer.style(f"  {err}", fg=typer.colors.RED), err=True)
        raise typer.Exit(1)

    color = typer.colors.GREEN if response.status == "success" else typer.colors.YELLOW
    typer.echo(typer.style(f"Macro calendar sync: {response.status}", fg=color))
    for k, v in sorted(response.category_counts.items()):
        typer.echo(f"  {k}: {v}")
    typer.echo(f"Stored {response.stored_count} events from {response.fetched_count} fetched.")
    if response.errors:
        for err in response.errors:
            typer.echo(typer.style(f"  warning: {err}", fg=typer.colors.YELLOW))
