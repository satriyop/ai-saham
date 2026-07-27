"""
CLI commands for stock universe management.

Commands (all under `saham fetch universe`):
  saham fetch universe list      — show configured universes with counts
  saham fetch universe update    — refresh from Stockbit Exodus API
  saham fetch universe inspect   — explore Stockbit sectors and subsectors
  saham fetch universe create    — create custom universe from sector/subsector

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_universe_display import (
    render_create_result,
    render_discovery,
    render_inspect_result,
    render_update_result,
)
from src.adapters.cli.fetch_universe_factories import (
    create_create_use_case,
    create_inspect_use_case,
    create_provider_adapter,
    create_update_use_case,
)
from src.application.services.universe_loader import UNIVERSE_CONFIG_PATH, load_universe_meta
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.config.yaml_universe_config_store import YamlUniverseConfigStore

universe_app = typer.Typer(
    name="universe",
    help="Manage stock universe lists (broad indices + sectoral sub-groups)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@universe_app.command("list")
def universe_list(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to universes.yaml"),
    ] = None,
) -> None:
    """
    List configured ticker universes with last-updated date and ticker count.

    Example:
        saham fetch universe list
    """
    resolved_config = config_path or UNIVERSE_CONFIG_PATH
    meta = load_universe_meta(YamlUniverseConfigLoader(), resolved_config)

    if not meta:
        typer.echo(f"No universe config found at '{resolved_config}'.")
        typer.echo("Expected: config/universes.yaml")
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("Configured universes:")
    typer.echo(f"  {'NAME':<14} {'TICKERS':>8}  {'LAST UPDATED'}")
    typer.echo("  " + "-" * 40)
    for name, info in meta.items():
        typer.echo(f"  {name:<14} {info['count']:>8}  {info['updated']}")
    typer.echo("")
    typer.echo(f"Config file: {resolved_config}")
    typer.echo("")
    typer.echo("Usage: saham fetch market --universe <name>")
    typer.echo("       saham screen accum --universe <name>")


@universe_app.command("update")
def universe_update(
    universe_name: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe(s) to update, comma-separated (e.g. lq45,idx80). Omit for all.",
        ),
    ] = None,
    discover: Annotated[
        bool,
        typer.Option(
            "--discover", help="List all available universes from Stockbit without updating"
        ),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to universes.yaml"),
    ] = None,
) -> None:
    """
    Refresh universe ticker lists from Stockbit Exodus API.

    Discovers all IDX index universes (LQ45, IDX30, IDX80, JII, MBX, BUMN20)
    and sectoral universes (finance, energy, health, etc.) by querying the
    Stockbit sector/subsector API, then fetches live constituent lists and
    updates config/universes.yaml.

    Requires an active Stockbit session (run `saham fetch stockbit login` first).

    Examples:
        saham fetch universe update                     # update all known universes
        saham fetch universe update --universe lq45     # update only LQ45
        saham fetch universe update --universe lq45,idx80
        saham fetch universe update --discover          # list available without updating
    """
    cfg = load_app_config()
    resolved_config = config_path or Path("config/universes.yaml")

    _STOCKBIT_PROFILE_DIR = Path(cfg.storage.stockbit_profile_dir)
    if not _STOCKBIT_PROFILE_DIR.exists():
        typer.echo("")
        typer.echo("No Stockbit session found. Run `saham fetch stockbit login` first.")
        typer.echo("")
        typer.echo("Manual alternative:")
        typer.echo("  1. Visit https://www.idx.co.id/en/market-data/indexes/")
        typer.echo("  2. Edit config/universes.yaml with updated tickers")
        raise typer.Exit(1)

    provider = create_provider_adapter()
    config_store = YamlUniverseConfigStore(resolved_config)
    use_case = create_update_use_case(provider, config_store)

    typer.echo("")
    typer.echo("Discovering IDX index universes from Stockbit...")

    try:
        result = use_case.execute(
            universe_name=universe_name,
            discover=discover,
            today=date.today(),
        )
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    if discover and isinstance(result, tuple):
        render_discovery(result)
        return

    if isinstance(result, tuple):
        render_discovery(result)
        return

    if not result.updated:
        typer.echo("")
        typer.echo("No universes updated — all fetches failed.")
        raise typer.Exit(1)

    render_update_result(result)


@universe_app.command("inspect")
def universe_inspect(
    sector_id: Annotated[
        Optional[int],
        typer.Option(
            "--sector", "-s", help="Drill into a specific sector ID to show its subsectors"
        ),
    ] = None,
    subsector_id: Annotated[
        Optional[int],
        typer.Option(
            "--subsector", "-b", help="Drill into a specific subsector ID to show its companies"
        ),
    ] = None,
    with_count: Annotated[
        bool,
        typer.Option("--count", "-c", help="Fetch company count for each subsector (slower)"),
    ] = False,
) -> None:
    """
    Inspect available Stockbit sectors and subsectors, and drill down to companies.

    Without parameters: lists all top-level sectors with their IDs.
    With --sector ID: lists all subsectors inside that sector, optionally
    with company counts per subsector (--count).
    With --sector ID and --subsector ID: lists all companies inside that subsector.

    Requires an active Stockbit session (run `saham fetch stockbit login` first).

    Examples:
        saham fetch universe inspect                            # list all sectors
        saham fetch universe inspect --sector 5                 # subsectors of sector 5
        saham fetch universe inspect --sector 5 --subsector 49  # companies in subsector 49
    """
    if subsector_id is not None and sector_id is None:
        typer.echo(
            "Error: --sector (-s) ID is required when specifying --subsector (-b) ID.", err=True
        )
        raise typer.Exit(1)

    provider = create_provider_adapter()
    use_case = create_inspect_use_case(provider)

    try:
        result = use_case.execute(
            sector_id=sector_id,
            subsector_id=subsector_id,
            with_count=with_count,
        )
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    render_inspect_result(result)


@universe_app.command("create")
def universe_create(
    name: Annotated[
        str,
        typer.Argument(help="Name of the new universe (e.g. food_beverage)"),
    ],
    sector_id: Annotated[
        int,
        typer.Option("--sector", "-s", help="Sector ID to query"),
    ],
    subsector_id: Annotated[
        Optional[int],
        typer.Option("--subsector", "-b", help="Subsector ID to query"),
    ] = None,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to universes.yaml"),
    ] = None,
) -> None:
    """
    Create a custom universe from a Stockbit sector/subsector and save/sync it
    to universes.yaml.

    Requires an active Stockbit session (run `saham fetch stockbit login` first).

    Examples:
        saham fetch universe create food_retail -s 1 -b 10
        saham fetch universe create consumer_primer -s 1
    """
    resolved_config = config_path or Path("config/universes.yaml")

    provider = create_provider_adapter()
    config_store = YamlUniverseConfigStore(resolved_config)
    use_case = create_create_use_case(provider, config_store)

    typer.echo("")
    if subsector_id is not None:
        typer.echo(f"Fetching companies for sector {sector_id} subsector {subsector_id}...")
    else:
        typer.echo(f"Fetching subsectors for sector {sector_id}...")

    try:
        result = use_case.execute(
            name=name,
            sector_id=sector_id,
            subsector_id=subsector_id,
            today=date.today(),
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    render_create_result(result)
