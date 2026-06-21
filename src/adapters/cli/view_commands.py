"""
Read-only data browsing commands.

Layer: Adapter
"""

from pathlib import Path

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
