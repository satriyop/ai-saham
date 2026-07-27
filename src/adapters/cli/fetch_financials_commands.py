"""
CLI command for multi-period financial statement fetch.

`saham fetch financials` — pulls quarterly/annual income-statement line items
from yfinance into local SQLite. Thin adapter: parse input, wire ports, call
use case, format output. Freshness policy lives in FetchFinancialsUseCase.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.fetch_financials_use_case import (
    DEFAULT_FINANCIALS_TTL_DAYS,
    FetchFinancialsRequest,
    FetchFinancialsTickerResult,
    FetchFinancialsUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.data_providers.yahoo_financials import YahooFinancialsProvider
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_company_financials_repository import (
    SQLiteCompanyFinancialsRepository,
)


def fetch_financials(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force provider fetch even if cache is fresh"),
    ] = False,
    ttl_days: Annotated[
        int,
        typer.Option(
            "--ttl-days",
            help="Skip network fetch when cache is newer than this many days",
            min=0,
        ),
    ] = DEFAULT_FINANCIALS_TTL_DAYS,
    quarterly: Annotated[
        bool,
        typer.Option("--quarterly/--no-quarterly", help="Include quarterly statements"),
    ] = True,
    annual: Annotated[
        bool,
        typer.Option("--annual/--no-annual", help="Include annual statements"),
    ] = True,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """Fetch multi-period financial statements into the local cache.

    Primary source: Yahoo Finance (yfinance). Stores income-statement line
    items (revenue, net income, interest income, EPS) per quarter/year.
    Distinct from Stockbit keystats ratios in `company_fundamentals`.

    Examples:
        saham fetch financials BBCA BBRI
        saham fetch financials --universe lq45
        saham fetch financials BBCA --refresh
        saham fetch financials BBCA --no-annual
    """
    if not quarterly and not annual:
        typer.echo("Error: enable at least one of --quarterly or --annual.", err=True)
        raise typer.Exit(1)

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(resolved_db),
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to update. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    provider = YahooFinancialsProvider(market_suffix=cfg.market.suffix)
    repository = SQLiteCompanyFinancialsRepository(resolved_db)
    use_case = FetchFinancialsUseCase(provider=provider, repository=repository)

    response = use_case.execute(
        FetchFinancialsRequest(
            tickers=tuple(ticker_list),
            force_refresh=refresh,
            ttl_days=ttl_days,
            include_quarterly=quarterly,
            include_annual=annual,
        )
    )

    for result in response.results:
        typer.echo(_format_row(result))

    typer.echo(
        f"\nDone: {response.fetched_count} fetched, "
        f"{response.cached_count} cached, "
        f"{response.error_count} errors "
        f"({len(response.results)} tickers)."
    )
    if response.error_count and response.fetched_count == 0 and response.cached_count == 0:
        raise typer.Exit(1)


def _format_row(result: FetchFinancialsTickerResult) -> str:
    latest = result.latest_period_end.isoformat() if result.latest_period_end else "-"
    if result.status == "cached":
        return f"  {result.ticker}: cached  periods={result.periods_stored}  latest={latest}"
    if result.status == "fetched":
        return f"  {result.ticker}: fetched periods={result.periods_stored}  latest={latest}"
    if result.status == "empty":
        return f"  {result.ticker}: empty   {result.error or 'no data'}"
    return f"  {result.ticker}: error   {result.error or 'unknown'}"
