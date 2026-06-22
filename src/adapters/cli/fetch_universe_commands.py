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

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.universe_loader import load_universe_meta

universe_app = typer.Typer(
    name="universe",
    help="Manage stock universe lists (broad indices + sectoral sub-groups)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

from src.infrastructure.config.app_config import APP_CFG

_STOCKBIT_PROFILE_DIR = Path(APP_CFG.storage.stockbit_profile_dir)


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
    import time
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

    existing: dict = {}
    if resolved_config.exists():
        try:
            with open(resolved_config) as f:
                existing = yaml.safe_load(f) or {}
        except Exception as e:
            typer.echo(f"Warning: could not read {resolved_config}: {e}")

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

        token = provider._get_token()
        universe_prov = StockbitUniverseProvider(broker_provider=provider)
    except ImportError as e:
        typer.echo(f"Playwright not installed: {e}")
        raise typer.Exit(1)

    def _get(url: str) -> dict | None:
        from src.infrastructure.browser.playwright_stockbit import _exodus_get
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
        unknown = [
            t for t in targets 
            if t not in available and not (t in existing and isinstance(existing[t], dict) and "sector_id" in existing[t])
        ]
        if unknown:
            typer.echo(f"Unknown universe(s): {', '.join(unknown)}")
            typer.echo(f"Available: {', '.join(sorted(available.keys()))}")
            raise typer.Exit(1)
    else:
        # Default: all discovered universes except ihsg, plus custom ones
        targets = [k for k in available if k != "ihsg"]
        for k, v in existing.items():
            if isinstance(v, dict) and "sector_id" in v and k not in targets:
                targets.append(k)

    today_str = date.today().isoformat()
    updated: dict[str, list[str]] = {}
    failed: list[str] = []

    typer.echo(f"Fetching {len(targets)} universe(s): {', '.join(targets)}")
    typer.echo("")

    for key in targets:
        is_custom = key in existing and isinstance(existing[key], dict) and "sector_id" in existing[key]
        utype = "custom" if is_custom else _utype(key)
        typer.echo(f"  {key:<14} [{utype}]...", nl=False)
        
        tickers = []
        if is_custom:
            cfg = existing[key]
            sector_id = cfg["sector_id"]
            subsector_id = cfg.get("subsector_id")
            
            try:
                if subsector_id is not None:
                    url = f"https://exodus.stockbit.com/emitten/v3/sector/{sector_id}/subsector/{subsector_id}/company"
                    comp_body = _get(url)
                    if comp_body is not None:
                        items = _extract_list(comp_body, "companies", "list", "items", "stocks")
                        for item in items:
                            code = (
                                item.get("ticker")
                                or item.get("code")
                                or item.get("stock_code")
                                or item.get("symbol")
                                or (item.get("stock_detail") or {}).get("code")
                            )
                            if code and isinstance(code, str) and code.strip():
                                tickers.append(code.strip().upper())
                else:
                    body = _get(f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors")
                    if body is not None:
                        subsectors = _extract_list(body, "subsectors", "list", "items")
                        for i, sub in enumerate(subsectors):
                            sub_id = sub.get("id") or sub.get("subsector_id")
                            if sub_id is None:
                                continue
                            if i > 0:
                                time.sleep(0.2)
                            url = f"https://exodus.stockbit.com/emitten/v3/sector/{sector_id}/subsector/{sub_id}/company"
                            comp_body = _get(url)
                            if comp_body is None:
                                tickers = []
                                break
                            items = _extract_list(comp_body, "companies", "list", "items", "stocks")
                            for item in items:
                                code = (
                                    item.get("ticker")
                                    or item.get("code")
                                    or item.get("stock_code")
                                    or item.get("symbol")
                                    or (item.get("stock_detail") or {}).get("code")
                                )
                                if code and isinstance(code, str) and code.strip():
                                    tickers.append(code.strip().upper())
            except Exception:
                tickers = []
            
            tickers = sorted(set(tickers))
        else:
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
        if key in existing and isinstance(existing[key], dict):
            existing[key]["updated"] = today_str
            existing[key]["tickers"] = tickers
        else:
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
    subsector_id: Annotated[
        Optional[int],
        typer.Option("--subsector", "-b", help="Drill into a specific subsector ID to show its companies"),
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
        saham fetch universe inspect --sector 5 --subsector 49  # companies in subsector 49 of sector 5
    """
    if not _STOCKBIT_PROFILE_DIR.exists():
        typer.echo("No Stockbit session. Run `saham fetch stockbit login` first.")
        raise typer.Exit(1)

    if subsector_id is not None and sector_id is None:
        typer.echo("Error: --sector (-s) ID is required when specifying --subsector (-b) ID.", err=True)
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
        console().print("")
        console().print("Fetching all sectors from Stockbit...")
        body = _get("https://exodus.stockbit.com/emitten/sectors")
        sectors = _extract_list(body, "sectors", "list", "items")

        if not sectors:
            typer.echo("No sectors returned. Check session or response shape.")
            raise typer.Exit(1)

        table = compact_table()
        table.add_column("ID", style="bold cyan")
        table.add_column("Sector Name")
        table.add_column("Companies", justify="right")

        for s in sectors:
            sid = s.get("id") or s.get("sector_id") or "?"
            name = s.get("name") or s.get("sector_name") or "?"
            count = s.get("total_company") or s.get("company_count") or ""
            table.add_row(str(sid), name, str(count) if count else "—")

        console().print("")
        console().print(panel(table, title="STOCKBIT SECTORS"))
        console().print("Tip: drill into a sector with --sector <ID> (e.g., -s 70)")
        console().print("     Known useful IDs: 88=Broad Indices  70=Sectoral Indices")
        console().print("")

    elif subsector_id is None:
        console().print("")
        console().print(f"Fetching subsectors for sector {sector_id}...")
        body = _get(f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors")
        subsectors = _extract_list(body, "subsectors", "list", "items")

        if not subsectors:
            typer.echo(f"No subsectors found for sector {sector_id}.")
            raise typer.Exit(1)

        table = compact_table()
        table.add_column("Sub-ID", style="bold cyan")
        table.add_column("Subsector Name")
        table.add_column("Companies", justify="right")

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
            table.add_row(str(sub_id), name, count_str)

        console().print("")
        console().print(panel(table, title=f"SUBSECTORS OF SECTOR {sector_id}"))
        console().print(f"Tip: drill into a subsector with: --sector {sector_id} --subsector <SUB-ID>")
        console().print("")

    else:
        console().print("")
        console().print(f"Fetching companies for sector {sector_id} subsector {subsector_id}...")
        url = f"https://exodus.stockbit.com/emitten/v3/sector/{sector_id}/subsector/{subsector_id}/company"
        comp_body = _get(url)
        items = _extract_list(comp_body, "companies", "list", "items", "stocks")

        if not items:
            typer.echo(f"No companies found in sector {sector_id} subsector {subsector_id}.")
            raise typer.Exit(1)

        table = compact_table()
        table.add_column("Ticker", style="bold cyan")
        table.add_column("Company Name")

        for item in items:
            code = (
                item.get("ticker")
                or item.get("code")
                or item.get("stock_code")
                or item.get("symbol")
                or (item.get("stock_detail") or {}).get("code")
                or "?"
            )
            name = (
                item.get("name")
                or item.get("company_name")
                or item.get("company")
                or (item.get("stock_detail") or {}).get("name")
                or "Unknown Name"
            )
            table.add_row(str(code).upper(), name)

        console().print("")
        console().print(panel(table, title=f"COMPANIES IN SUBSECTOR {subsector_id} (Sector {sector_id})"))
        console().print(f"Total: {len(items)} company(ies)")
        console().print("")


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
    Create a custom universe from a Stockbit sector/subsector and save/sync it to universes.yaml.

    Requires an active Stockbit session (run `saham fetch stockbit login` first).

    Examples:
        saham fetch universe create food_retail -s 1 -b 10
        saham fetch universe create consumer_primer -s 1
    """
    import yaml
    import time
    from datetime import date

    resolved_config = config_path or Path("config/universes.yaml")
    universe_key = name.strip().lower()

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

    tickers = []

    if subsector_id is not None:
        console().print("")
        console().print(f"Fetching companies for sector {sector_id} subsector {subsector_id}...")
        url = f"https://exodus.stockbit.com/emitten/v3/sector/{sector_id}/subsector/{subsector_id}/company"
        comp_body = _get(url)
        if comp_body is None:
            typer.echo(f"Error: Failed to fetch data for sector {sector_id} subsector {subsector_id}.", err=True)
            raise typer.Exit(1)

        items = _extract_list(comp_body, "companies", "list", "items", "stocks")
        if not items:
            typer.echo(f"No companies found in sector {sector_id} subsector {subsector_id}.", err=True)
            raise typer.Exit(1)

        for item in items:
            code = (
                item.get("ticker")
                or item.get("code")
                or item.get("stock_code")
                or item.get("symbol")
                or (item.get("stock_detail") or {}).get("code")
            )
            if code and isinstance(code, str) and code.strip():
                tickers.append(code.strip().upper())
    else:
        console().print("")
        console().print(f"Fetching subsectors for sector {sector_id}...")
        body = _get(f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors")
        if body is None:
            typer.echo(f"Error: Failed to fetch subsectors for sector {sector_id}.", err=True)
            raise typer.Exit(1)

        subsectors = _extract_list(body, "subsectors", "list", "items")
        if not subsectors:
            typer.echo(f"No subsectors found for sector {sector_id}.", err=True)
            raise typer.Exit(1)

        console().print(f"Found {len(subsectors)} subsector(s). Fetching constituents...")

        for i, sub in enumerate(subsectors):
            sub_id = sub.get("id") or sub.get("subsector_id")
            sub_name = sub.get("name") or sub.get("subsector_name") or f"Subsector {sub_id}"
            if sub_id is None:
                continue

            if i > 0:
                time.sleep(0.2)

            console().print(f"  [{i+1}/{len(subsectors)}] Fetching subsector {sub_id} ({sub_name})...")
            url = f"https://exodus.stockbit.com/emitten/v3/sector/{sector_id}/subsector/{sub_id}/company"
            comp_body = _get(url)
            if comp_body is None:
                typer.echo(f"Error: Failed to fetch data for sector {sector_id} subsector {sub_id}. Aborting transaction to keep config safe.", err=True)
                raise typer.Exit(1)

            items = _extract_list(comp_body, "companies", "list", "items", "stocks")
            for item in items:
                code = (
                    item.get("ticker")
                    or item.get("code")
                    or item.get("stock_code")
                    or item.get("symbol")
                    or (item.get("stock_detail") or {}).get("code")
                )
                if code and isinstance(code, str) and code.strip():
                    tickers.append(code.strip().upper())

    tickers = sorted(set(tickers))
    if not tickers:
        typer.echo("No valid company tickers extracted.", err=True)
        raise typer.Exit(1)

    # Load existing config
    existing: dict = {}
    if resolved_config.exists():
        try:
            with open(resolved_config) as f:
                existing = yaml.safe_load(f) or {}
        except Exception as e:
            typer.echo(f"Warning: could not read {resolved_config}: {e}")

    today_str = date.today().isoformat()
    existing[universe_key] = {
        "updated": today_str,
        "tickers": tickers,
        "sector_id": sector_id,
    }
    if subsector_id is not None:
        existing[universe_key]["subsector_id"] = subsector_id

    # Write config back
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

        console().print("")
        table = compact_table(show_header=False)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")
        table.add_row("Universe Name", universe_key)
        table.add_row("Tickers Count", str(len(tickers)))
        table.add_row("Tickers", ", ".join(tickers[:10]) + (f", ... (+{len(tickers) - 10} more)" if len(tickers) > 10 else ""))
        table.add_row("Config File", str(resolved_config))

        console().print(
            panel(
                table,
                title="CUSTOM UNIVERSE CREATED & SYNCED"
            )
        )
        console().print("")
    except Exception as e:
        typer.echo(f"Error writing {resolved_config}: {e}", err=True)
        raise typer.Exit(1)

