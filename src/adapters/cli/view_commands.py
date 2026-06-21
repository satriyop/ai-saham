"""
Read-only data browsing commands.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from typer.core import TyperGroup

from src.adapters.cli.broker_commands import (
    broker_flow,
    broker_history_view,
    broker_mappings,
    broker_status,
    broker_top,
    broker_top_foreign_view,
)


class _ViewGroup(TyperGroup):
    """TyperGroup subclass that routes unknown first-arg to the 'ticker' command.

    Allows `saham view BBCA` to work identically to `saham view ticker BBCA`
    while preserving normal subcommand routing for `saham view broker ...`.
    """

    def parse_args(self, ctx: typer.Context, args: list) -> list:
        if args and not args[0].startswith("-") and args[0] not in self.commands:
            args = ["ticker"] + list(args)
        return super().parse_args(ctx, args)


view_app = typer.Typer(
    cls=_ViewGroup,
    name="view",
    help="Read-only data browsing — inspect already-fetched local data.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

broker_view_app = typer.Typer(
    name="broker",
    help="Browse cached broker and foreign-flow data.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

broker_view_app.command("status")(broker_status)
broker_view_app.command("flow")(broker_flow)
broker_view_app.command("top")(broker_top)
broker_view_app.command("history")(broker_history_view)
broker_view_app.command("top-foreign")(broker_top_foreign_view)
broker_view_app.command("mappings")(broker_mappings)

view_app.add_typer(broker_view_app, name="broker")


@view_app.command("ticker", hidden=True)
def view_ticker(
    ticker: str = typer.Argument(..., help="Ticker symbol (e.g. BBCA)"),
) -> None:
    """Show all cached data for a ticker."""
    from src.adapters.cli.view_ticker_display import show_ticker_view
    show_ticker_view(ticker.upper(), db_path=Path("data.db"))


@view_app.command("universe")
def view_universe(
    name: Annotated[
        Optional[str],
        typer.Argument(help="Universe name (e.g. lq45, bank, finance). Omit to list all."),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option("--sort", "-s", help="Sort rows by: flow|change|volume|ticker"),
    ] = "flow",
    top_n: Annotated[
        Optional[int],
        typer.Option("--top", "-n", help="Show only the top N rows"),
    ] = None,
    as_of: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Show data as of this date (YYYY-MM-DD). Default: latest cached."),
    ] = None,
    db_path: Annotated[
        Path,
        typer.Option("--db", hidden=True),
    ] = Path("data.db"),
) -> None:
    """Show a market overview for all tickers in a named universe.

    Displays latest close price, daily change %, volume, and foreign flow
    for every ticker in the universe, sorted by strongest foreign accumulation.
    All data is read from the local cache — no network required.

    Examples:
        saham view universe lq45
        saham view universe bank --sort change
        saham view universe finance --top 20 --sort flow
        saham view universe lq45 --date 2026-06-20
        saham view universe          # list all configured universes
    """
    from src.adapters.cli.view_universe_display import (
        display_universe_list,
        display_universe_view,
    )
    from src.application.services.universe_loader import (
        UNIVERSE_CONFIG_PATH,
        UniverseNotFoundError,
        load_universe_meta,
    )
    from src.application.use_case.view_universe_summary import build_universe_view

    _valid_sorts = {"flow", "change", "volume", "ticker"}
    if sort_by not in _valid_sorts:
        typer.echo(
            f"Invalid --sort '{sort_by}'. Choose from: {', '.join(sorted(_valid_sorts))}",
            err=True,
        )
        raise typer.Exit(1)

    if name is None:
        meta = load_universe_meta(UNIVERSE_CONFIG_PATH)
        if not meta:
            typer.echo("No universe config found. Run: saham fetch universe update")
            raise typer.Exit(1)
        display_universe_list(meta)
        return

    as_of_date = None
    if as_of:
        try:
            as_of_date = date.fromisoformat(as_of)
        except ValueError:
            typer.echo(f"Invalid date format: '{as_of}'. Expected YYYY-MM-DD.", err=True)
            raise typer.Exit(1)

    try:
        result = build_universe_view(
            universe_name=name.lower(),
            db_path=db_path,
            as_of_date=as_of_date,
        )
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    except UniverseNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    display_universe_view(result, sort_by=sort_by, top_n=top_n)
