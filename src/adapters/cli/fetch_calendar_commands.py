"""
CLI command for the market-wide corporate action calendar sync.

`saham fetch calendar` — fetches the 9 market-wide Stockbit corporate action
calendar endpoints once, stores them, and reports per-type counts. Thin adapter:
parses input, constructs dependencies, makes one use-case call, formats output.
All fetch/freshness policy lives in the use case.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.sync_corporate_action_calendar_use_case import (
    SyncCorporateActionCalendarRequest,
    SyncCorporateActionCalendarUseCase,
)
from src.domain.value_objects.corporate_action_calendar import CorporateActionType
from src.infrastructure.browser.stockbit_corporate_action_calendar import (
    StockbitCorporateActionCalendarProvider,
)
from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)

# Default --types order (all 9 supported v1 types).
_DEFAULT_TYPES = "dividend,stock_split,reverse_split,rights_issue,bonus,tender_offer,rups,pubex,ipo"


def _parse_types(raw: str) -> tuple[CorporateActionType, ...]:
    parsed: list[CorporateActionType] = []
    for token in raw.split(","):
        name = token.strip()
        if not name:
            continue
        try:
            parsed.append(CorporateActionType(name))
        except ValueError:
            supported = ", ".join(t.value for t in CorporateActionType)
            typer.echo(
                typer.style(
                    f"Unsupported event type: {name!r}. Supported: {supported}",
                    fg=typer.colors.RED,
                ),
                err=True,
            )
            raise typer.Exit(1)
    return tuple(parsed)


def fetch_calendar(
    types: Annotated[
        Optional[str],
        typer.Option("--types", help="Comma-separated normalized event types"),
    ] = None,
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
    Sync the market-wide corporate action calendar from Stockbit.

    Fetches dividend, stock split, reverse split, rights issue, bonus, tender
    offer, RUPS, public expose, and IPO events into normalized SQLite tables.

    Requires an active Stockbit session (run 'saham fetch stockbit login').

    Examples:
        saham fetch calendar
        saham fetch calendar --types dividend,ipo
        saham fetch calendar --refresh
    """
    event_types = _parse_types(types or _DEFAULT_TYPES)
    resolved_db = db_path or DEFAULT_DB_PATH

    session = get_stockbit_session()
    if session is None or not session.authenticated:
        typer.echo(
            typer.style("Not authenticated.", fg=typer.colors.RED)
            + " Run: saham fetch stockbit login",
            err=True,
        )
        raise typer.Exit(1)

    provider = StockbitCorporateActionCalendarProvider(api_client=session.api_client)
    repository = SQLiteCorporateActionCalendarRepository(resolved_db)
    use_case = SyncCorporateActionCalendarUseCase(provider=provider, repository=repository)

    response = use_case.execute(
        SyncCorporateActionCalendarRequest(
            event_types=event_types,
            sync_date=date.today(),
            force_remote_fetch=refresh,
        )
    )

    if response.from_cache:
        typer.echo("Already synced today — use --refresh to force.")
        return

    if response.status == "failed":
        typer.echo(typer.style("Calendar sync failed.", fg=typer.colors.RED), err=True)
        for err in response.errors:
            typer.echo(typer.style(f"  {err}", fg=typer.colors.RED), err=True)
        raise typer.Exit(1)

    color = typer.colors.GREEN if response.status == "success" else typer.colors.YELLOW
    typer.echo(typer.style(f"Calendar sync: {response.status}", fg=color))
    for k, v in sorted(response.event_type_counts.items()):
        typer.echo(f"  {k}: {v}")
    typer.echo(f"Stored {response.stored_count} events from {response.fetched_count} fetched.")
    if response.errors:
        for err in response.errors:
            typer.echo(typer.style(f"  warning: {err}", fg=typer.colors.YELLOW))
