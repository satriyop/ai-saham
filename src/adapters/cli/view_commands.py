"""
Read-only data browsing commands.

Layer: Adapter

Taxonomy (clean break):
  view <TICKER>              → ticker show (dashboard shorthand)
  view ticker <verb> <TICKER>  stock deep-dives
  view broker <verb> …         desk / universe / meta
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from typer.core import TyperGroup

from src.adapters.cli.view_broker_commands import broker_view_app
from src.adapters.cli.view_ticker_commands import ticker_view_app
from src.infrastructure.config.app_config import load_app_config

# Retired view subcommands that must not be rewritten as ticker show.
_RETIRED_VIEW_TOKENS = frozenset(
    {
        "market-context",
    }
)
_RETIRED_VIEW_HINTS = {
    "market-context": "Retired. Use: saham inspect regime",
}


class _ViewGroup(TyperGroup):
    """Route bare tickers to `ticker show` while preserving fixed subgroups.

    `saham view BBCA` → `saham view ticker show BBCA`
    `saham view ticker top-brokers BBCA` is unchanged (first token is `ticker`).
    Retired tokens (e.g. market-context) fail closed instead of ticker-show.
    """

    def parse_args(self, ctx: typer.Context, args: list) -> list:
        if args and not args[0].startswith("-"):
            token = args[0]
            if token in _RETIRED_VIEW_TOKENS:
                typer.echo(
                    _RETIRED_VIEW_HINTS.get(token, f"Retired view command: {token}"),
                    err=True,
                )
                raise SystemExit(2)
            if token not in self.commands:
                # Bare subject → stock dashboard
                args = ["ticker", "show"] + list(args)
        return super().parse_args(ctx, args)


view_app = typer.Typer(
    cls=_ViewGroup,
    name="view",
    help=(
        "Read-only browse of already-fetched local data (not a decision surface).\n\n"
        "Needs data: `saham fetch …`.\n"
        "Stock overview: `saham view BBCA` or `saham view ticker show BBCA`.\n"
        "Stock deep-dives: `saham view ticker <verb> <TICKER>` "
        "(top-brokers | flow | foreign-history | distribution | financials).\n"
        "Desk / universe: `saham view broker <verb> …` "
        "(top-foreign ranking cache after `fetch broker-top-foreign`).\n"
        "Decisions: `saham plan swing` / `saham assess pre-open`. "
        "Market regime: `saham inspect regime` (not view)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

view_app.add_typer(ticker_view_app, name="ticker")
view_app.add_typer(broker_view_app, name="broker")


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
        typer.Option(
            "--date",
            "-d",
            help="Show data as of this date (YYYY-MM-DD). Default: latest cached.",
        ),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", hidden=True),
    ] = None,
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
    from src.adapters.cli.cli_errors import (
        raise_data_unavailable,
        raise_user_error,
        resolve_cli_db_path,
    )
    from src.adapters.cli.view_universe_display import (
        display_universe_list,
        display_universe_view,
    )
    from src.application.services.universe_loader import (
        UNIVERSE_CONFIG_PATH,
        UniverseNotFoundError,
        load_universe_meta,
    )
    from src.application.use_case.view_universe_summary_use_case import build_universe_view
    from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader

    db_path = resolve_cli_db_path(db_path, configured_default=load_app_config().storage.db_path)
    loader = YamlUniverseConfigLoader()

    _valid_sorts = {"flow", "change", "volume", "ticker"}
    if sort_by not in _valid_sorts:
        raise_user_error(
            f"Invalid --sort '{sort_by}'. Choose from: {', '.join(sorted(_valid_sorts))}"
        )

    if name is None:
        meta = load_universe_meta(loader, UNIVERSE_CONFIG_PATH)
        if not meta:
            raise_data_unavailable(
                "No universe config found.",
                tip="Run: saham fetch universe update",
            )
        display_universe_list(meta)
        return

    as_of_date = None
    if as_of:
        try:
            as_of_date = date.fromisoformat(as_of)
        except ValueError:
            raise_user_error(f"Invalid date format: '{as_of}'. Expected YYYY-MM-DD.")

    try:
        from src.infrastructure.persistence.sqlite_universe_summary_provider import (
            SQLiteUniverseSummaryProvider,
        )

        provider = SQLiteUniverseSummaryProvider(db_path)
        result = build_universe_view(
            universe_name=name.lower(),
            loader=loader,
            as_of_date=as_of_date,
            provider=provider,
        )
    except FileNotFoundError as e:
        raise_data_unavailable(str(e), tip="Run: saham fetch universe update")
    except UniverseNotFoundError as e:
        raise_user_error(str(e), tip="See: saham fetch universe list")

    display_universe_view(result, sort_by=sort_by, top_n=top_n)
