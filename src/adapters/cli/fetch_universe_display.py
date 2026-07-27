"""
Display/render helpers for universe CLI commands.

Layer: Adapter
"""

import typer

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.dto.universe_management import (
    UniverseCreateResult,
    UniverseDiscoverItem,
    UniverseInspectResult,
    UniverseUpdateResult,
)


def render_discovery(items: tuple[UniverseDiscoverItem, ...]) -> None:
    """Render universe discovery results."""
    typer.echo("")
    typer.echo(f"  {'UNIVERSE KEY':<16} {'TYPE':<12} {'SUBSECTOR ID'}")
    typer.echo("  " + "─" * 44)
    for item in items:
        typer.echo(f"  {item.key:<16} {item.universe_type:<12} {item.subsector_id}")
    typer.echo("")
    typer.echo(f"Total: {len(items)} universe(s) available")


def render_update_result(result: UniverseUpdateResult) -> None:
    """Render universe update results."""
    typer.echo("")
    for item in result.updated:
        delta_str = (
            f"+{item.delta}" if item.delta > 0 else str(item.delta) if item.delta < 0 else "="
        )
        typer.echo(
            f"  {item.key:<14} [{item.universe_type}]... "
            f"{len(item.tickers)} tickers ({delta_str} vs prev)"
        )
    typer.echo("")
    typer.echo(f"Updated {result.config_path}  ({len(result.updated)} universe(s))")
    if result.failed:
        typer.echo(typer.style(f"Failed: {', '.join(result.failed)}", fg=typer.colors.YELLOW))


def render_inspect_result(result: UniverseInspectResult) -> None:
    """Render universe inspect results."""
    console().print("")
    table = compact_table()
    table.add_column("ID", style="bold cyan")
    table.add_column("Name")
    table.add_column("Count", justify="right")

    for row in result.rows:
        table.add_row(row.id, row.name, row.count)

    console().print(panel(table, title=result.title))

    if result.total is not None:
        console().print(f"Total: {result.total} company(ies)")

    for tip in result.tip_lines:
        console().print(tip)

    console().print("")


def render_create_result(result: UniverseCreateResult) -> None:
    """Render universe create results."""
    console().print("")
    table = compact_table(show_header=False)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")
    table.add_row("Universe Name", result.universe_name)
    table.add_row("Tickers Count", str(len(result.tickers)))
    tickers_str = ", ".join(result.tickers[:10])
    if len(result.tickers) > 10:
        tickers_str += f", ... (+{len(result.tickers) - 10} more)"
    table.add_row("Tickers", tickers_str)
    table.add_row("Config File", str(result.config_path))

    console().print(panel(table, title="CUSTOM UNIVERSE CREATED & SYNCED"))
    console().print("")
