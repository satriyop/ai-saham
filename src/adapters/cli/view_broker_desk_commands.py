"""
CLI: desk-centric view broker show | top-stocks | flow | history.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_desk_display import (
    display_desk_flow,
    display_desk_history,
    display_desk_show,
    display_desk_top_stocks,
)
from src.application.use_case.view_broker_desk_flow_use_case import (
    ViewBrokerDeskFlowRequest,
    ViewBrokerDeskFlowUseCase,
)
from src.application.use_case.view_broker_desk_history_use_case import (
    ViewBrokerDeskHistoryRequest,
    ViewBrokerDeskHistoryUseCase,
)
from src.application.use_case.view_broker_desk_show_use_case import (
    ViewBrokerDeskShowRequest,
    ViewBrokerDeskShowUseCase,
)
from src.application.use_case.view_broker_desk_top_stocks_use_case import (
    ViewBrokerDeskTopStocksRequest,
    ViewBrokerDeskTopStocksUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def _repo_and_codes(db_path: Path | None):
    resolved = db_path or Path(load_app_config().storage.db_path)
    ia_cfg = load_institutional_accumulation_config()
    return SQLiteBrokerRepository(resolved), ia_cfg.foreign_broker_codes


def broker_desk_show(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """Show compact desk dashboard from tracked broker_daily_flow."""
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskShowUseCase(
        repo, foreign_broker_codes=foreign
    ).execute(ViewBrokerDeskShowRequest(broker_code=code))
    if result is None:
        typer.echo(
            typer.style(f"No tracked desk data for {code.upper()}. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch market' with Stockbit first."
        )
        raise typer.Exit(1)
    display_desk_show(result)


def broker_desk_top_stocks(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    target_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date (YYYY-MM-DD), default: latest"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks per side", min=1, max=50),
    ] = 20,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """Rank stocks for a tracked desk on one session (broker_daily_flow)."""
    repo, foreign = _repo_and_codes(db_path)
    query_date = date.fromisoformat(target_date) if target_date else None
    result = ViewBrokerDeskTopStocksUseCase(
        repo, foreign_broker_codes=foreign
    ).execute(
        ViewBrokerDeskTopStocksRequest(
            broker_code=code, target_date=query_date, limit=limit
        )
    )
    if result is None:
        typer.echo(
            typer.style(f"No tracked desk data for {code.upper()}. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch market' with Stockbit first."
        )
        raise typer.Exit(1)
    display_desk_top_stocks(result)


def broker_desk_flow(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of trading days", min=1, max=365),
    ] = 10,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """Show desk aggregate net by day across cached tickers."""
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskFlowUseCase(
        repo, foreign_broker_codes=foreign
    ).execute(ViewBrokerDeskFlowRequest(broker_code=code, days=days))
    if result is None:
        typer.echo(
            typer.style(f"No tracked desk data for {code.upper()}. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch market' with Stockbit first."
        )
        raise typer.Exit(1)
    display_desk_flow(result)


def broker_desk_history(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    days: Annotated[
        int,
        typer.Option("--days", help="How many recent trading days", min=1, max=365),
    ] = 30,
    ticker: Annotated[
        Optional[str],
        typer.Option("--ticker", help="Pin to one stock ticker"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """Show desk per-ticker daily rows from broker_daily_flow."""
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskHistoryUseCase(
        repo, foreign_broker_codes=foreign
    ).execute(
        ViewBrokerDeskHistoryRequest(broker_code=code, days=days, ticker=ticker)
    )
    if result is None:
        typer.echo(
            typer.style(f"No tracked desk data for {code.upper()}. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch market' with Stockbit first."
        )
        raise typer.Exit(1)
    display_desk_history(result)
