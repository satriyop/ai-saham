"""
CLI commands for stock universe management.

Commands (all under `saham fetch universe`):
  saham fetch universe list      — show configured universes with counts
  saham fetch universe update    — refresh from Stockbit Exodus API
  saham fetch universe inspect   — explore Stockbit sectors and subsectors

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import load_universe_meta

universe_app = typer.Typer(
    name="universe",
    help="Manage stock universe lists (broad indices + sectoral sub-groups)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

_STOCKBIT_PROFILE_DIR = Path(".stockbit_profile")


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
    from src.application.services.universe_loader import UNIVERSE_CONFIG_PATH

    resolved_config = config_path or UNIVERSE_CONFIG_PATH
    meta = load_universe_meta(resolved_config)

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
        typer.Option("--universe", "-u", help="Universe(s) to update, comma-separated (e.g. lq45,idx80). Omit for all."),
    ] = None,
    discover: Annotated[
        bool,
        typer.Option("--discover", help="List all available universes from Stockbit without updating"),
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
    import yaml
    from datetime import date

    resolved_config = config_path or Path("config/universes.yaml")

    if not _STOCKBIT_PROFILE_DIR.exists():
        typer.echo("")
        typer.echo("No Stockbit session found. Run `saham fetch stockbit login` first.")
        typer.echo("")
        typer.echo("Manual alternative:")
        typer.echo("  1. Visit https://www.idx.co.id/en/market-data/indexes/")
        typer.echo("  2. Edit config/universes.yaml with updated tickers")
        raise typer.Exit(1)

    try:
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        from src.infrastructure.browser.stockbit_universe import (
            StockbitUniverseProvider,
            universe_type as _utype,
        )

        provider = StockbitPlaywrightBrokerProvider()
        if not provider.is_authenticated():
            typer.echo("Stockbit session expired. Run `saham fetch stockbit login` to refresh.")
            raise typer.Exit(1)

        universe_prov = StockbitUniverseProvider(broker_provider=provider)
    except ImportError as e:
        typer.echo(f"Playwright not installed: {e}")
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("Discovering IDX index universes from Stockbit...")
    available = universe_prov.list_available()

    if discover:
        typer.echo("")
        typer.echo(f"  {'UNIVERSE KEY':<16} {'TYPE':<12} {'SUBSECTOR ID'}")
        typer.echo("  " + "─" * 44)
        for key, (sid, _sector) in sorted(available.items()):
            typer.echo(f"  {key:<16} {_utype(key):<12} {sid}")
        typer.echo("")
        typer.echo(f"Total: {len(available)} universe(s) available")
        return

    if universe_name:
        targets = [u.strip().lower() for u in universe_name.split(",")]
        unknown = [t for t in targets if t not in available]
        if unknown:
            typer.echo(f"Unknown universe(s): {', '.join(unknown)}")
            typer.echo(f"Available: {', '.join(sorted(available.keys()))}")
            raise typer.Exit(1)
    else:
        # Default: all discovered universes except ihsg (full market, too large)
        targets = [k for k in available if k != "ihsg"]

    existing: dict = {}
    if resolved_config.exists():
        try:
            with open(resolved_config) as f:
                existing = yaml.safe_load(f) or {}
        except Exception as e:
            typer.echo(f"Warning: could not read {resolved_config}: {e}")

    today_str = date.today().isoformat()
    updated: dict[str, list[str]] = {}
    failed: list[str] = []

    typer.echo(f"Fetching {len(targets)} universe(s): {', '.join(targets)}")
    typer.echo("")

    for key in targets:
        utype = _utype(key)
        typer.echo(f"  {key:<14} [{utype}]...", nl=False)
        tickers = universe_prov.fetch(key)
        if tickers:
            updated[key] = tickers
            prev_count = len((existing.get(key) or {}).get("tickers") or [])
            delta = len(tickers) - prev_count
            delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "="
            typer.echo(typer.style(f" {len(tickers)} tickers ({delta_str} vs prev)", fg=typer.colors.GREEN))
        else:
            failed.append(key)
            typer.echo(typer.style(" FAILED", fg=typer.colors.RED))

    if not updated:
        typer.echo("")
        typer.echo("No universes updated — all fetches failed.")
        raise typer.Exit(1)

    for key, tickers in updated.items():
        existing[key] = {"updated": today_str, "tickers": tickers}

    header = (
        "# IDX Stock Universe Lists\n"
        "#\n"
        "# These lists are used by `saham fetch market` and `saham screen accum`\n"
        "# to define which tickers to scan.\n"
        "#\n"
        "# IDX rebalances LQ45 and IDX80 every February and August.\n"
        "# Auto-updated via: saham fetch universe update (Stockbit Exodus API)\n"
        "#\n"
        f"# Last updated: {today_str}\n\n"
    )

    try:
        resolved_config.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_config, "w") as f:
            f.write(header)
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True, sort_keys=True)
        typer.echo("")
        typer.echo(f"Updated {resolved_config}  ({len(updated)} universe(s))")
        if failed:
            typer.echo(typer.style(f"Failed: {', '.join(failed)}", fg=typer.colors.YELLOW))
    except Exception as e:
        typer.echo(f"Error writing {resolved_config}: {e}", err=True)
        raise typer.Exit(1)


@universe_app.command("inspect")
def universe_inspect(
    sector_id: Annotated[
        Optional[int],
        typer.Option("--sector", "-s", help="Drill into a specific sector ID to show its subsectors"),
    ] = None,
    with_count: Annotated[
        bool,
        typer.Option("--count", "-c", help="Fetch company count for each subsector (slower)"),
    ] = False,
) -> None:
    """
    Inspect available Stockbit sectors and subsectors.

    Without --sector: lists all top-level sectors with their IDs.
    With --sector ID: lists all subsectors inside that sector, optionally
    with company counts per subsector (--count).

    Requires an active Stockbit session (run `saham fetch stockbit login` first).

    Examples:
        saham fetch universe inspect                # list all sectors
        saham fetch universe inspect --sector 5     # subsectors of sector 5
        saham fetch universe inspect --sector 5 --count
    """
    if not _STOCKBIT_PROFILE_DIR.exists():
        typer.echo("No Stockbit session. Run `saham fetch stockbit login` first.")
        raise typer.Exit(1)

    try:
        from src.infrastructure.browser.playwright_stockbit import (
            StockbitPlaywrightBrokerProvider,
            _exodus_get,
        )
        provider = StockbitPlaywrightBrokerProvider()
        if not provider.is_authenticated():
            typer.echo("Session expired. Run `saham fetch stockbit login` to refresh.")
            raise typer.Exit(1)
        token = provider._get_token()
    except ImportError as e:
        typer.echo(f"Playwright not installed: {e}")
        raise typer.Exit(1)

    def _get(url: str) -> dict | None:
        return _exodus_get(url, token)

    def _extract_list(body: dict | None, *keys: str) -> list[dict]:
        if not body:
            return []
        data = body.get("data")
        if isinstance(data, list):
            return [i for i in data if isinstance(i, dict)]
        if isinstance(data, dict):
            for k in keys:
                if isinstance(data.get(k), list):
                    return [i for i in data[k] if isinstance(i, dict)]
        return []

    if sector_id is None:
        typer.echo("")
        typer.echo("Fetching all sectors from Stockbit...")
        body = _get("https://exodus.stockbit.com/emitten/sectors")
        sectors = _extract_list(body, "sectors", "list", "items")

        if not sectors:
            typer.echo("No sectors returned. Check session or response shape.")
            raise typer.Exit(1)

        typer.echo("")
        typer.echo(f"  {'ID':<8} {'SECTOR NAME'}")
        typer.echo("  " + "─" * 40)
        for s in sectors:
            sid = s.get("id") or s.get("sector_id") or "?"
            name = s.get("name") or s.get("sector_name") or "?"
            count = s.get("total_company") or s.get("company_count") or ""
            count_str = f"  ({count} companies)" if count else ""
            typer.echo(f"  {str(sid):<8} {name}{count_str}")

        typer.echo("")
        typer.echo(f"Total: {len(sectors)} sector(s)")
        typer.echo("")
        typer.echo("Tip: drill into a sector with --sector <ID>")
        typer.echo("     Known useful IDs: 88=Broad Indices  70=Sectoral Indices")

    else:
        typer.echo("")
        typer.echo(f"Fetching subsectors for sector {sector_id}...")
        body = _get(f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors")
        subsectors = _extract_list(body, "subsectors", "list", "items")

        if not subsectors:
            typer.echo(f"No subsectors found for sector {sector_id}.")
            raise typer.Exit(1)

        typer.echo("")
        typer.echo(f"  {'SUB-ID':<12} {'SUBSECTOR NAME':<35} {'COMPANIES':>9}")
        typer.echo("  " + "─" * 58)

        for sub in subsectors:
            sub_id = sub.get("id") or sub.get("subsector_id") or "?"
            name = sub.get("name") or sub.get("subsector_name") or "?"
            count = sub.get("total_company") or sub.get("company_count") or ""

            if with_count and not count:
                url = f"https://exodus.stockbit.com/emitten/v3/sector/{sector_id}/subsector/{sub_id}/company"
                comp_body = _get(url)
                items = _extract_list(comp_body, "companies", "list", "items", "stocks")
                count = len(items)

            count_str = str(count) if count != "" else "?"
            typer.echo(f"  {str(sub_id):<12} {name:<35} {count_str:>9}")

        typer.echo("")
        typer.echo(f"Total: {len(subsectors)} subsector(s)")
        typer.echo("")
        typer.echo(f"Tip: fetch company list with:")
        typer.echo(f"     curl .../emitten/v3/sector/{sector_id}/subsector/<SUB-ID>/company")
