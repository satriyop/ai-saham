"""
CLI implementation for saham fetch status command.
Public command registration lives in lifecycle routers:
  saham fetch status
Layer: Adapter
"""

from pathlib import Path

import typer
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.application.use_case.get_system_status import (
    GetSystemStatusUseCase,
)
from src.infrastructure.persistence.sqlite_system_status_provider import (
    SQLiteSystemStatusProvider,
)

DEFAULT_DB_PATH = Path("data.db")


def status(
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db",
        help="Path to SQLite database",
    ),
) -> None:
    """
    Check data provider health and database freshness.

    Probes IDX API, Yahoo Finance, Stockbit session, and AI classifier.
    Reports latest data dates and row counts across all database tables.
    """
    # Inject dependencies and execute use case
    provider = SQLiteSystemStatusProvider(db_path=db_path)
    use_case = GetSystemStatusUseCase(provider=provider)
    response = use_case.execute()

    # Local Rich Console for fully colored interactive CLI table outputs
    console = Console()

    # 1. Data Provider Health Table
    health_table = Table(
        title="[bold cyan]Data Provider Health[/bold cyan]",
        box=ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    health_table.add_column("Provider", ratio=3)
    health_table.add_column("Status", justify="center", ratio=1)
    health_table.add_column("Details", ratio=6)
    health_table.add_column("Latency", justify="right", ratio=1)

    for p in response.providers:
        warning = "key" in p.label or "expired" in p.label
        icon = "[green]✅[/green]" if p.ok else ("[yellow]⚠[/yellow]" if warning else "[red]✗[/red]")
        ms_str = f"{p.ms}s" if p.ms else ""
        health_table.add_row(p.name, icon, p.label, ms_str)

    console.print("")
    console.print(health_table)
    console.print("")

    # 2. Data Freshness Table
    if not db_path.exists():
        panel = Panel(
            f"[yellow]No database found at [bold]{db_path}[/bold].[/yellow]\n\n"
            "Run: [bold cyan]saham fetch market <TICKER>[/bold cyan] to initialize.",
            title="[bold cyan]Data Freshness[/bold cyan]",
            border_style="yellow",
            expand=True,
        )
        console.print(panel)
        return

    if not response.freshness:
        console.print("[yellow]No database table freshness data found.[/yellow]")
        return

    freshness_table = Table(
        title="[bold cyan]Data Freshness[/bold cyan]",
        box=ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    freshness_table.add_column("Table", ratio=3)
    freshness_table.add_column("Source", ratio=2)
    freshness_table.add_column("Latest", ratio=2)
    freshness_table.add_column("Rows", justify="right", ratio=2)
    freshness_table.add_column("Status", ratio=3)

    for item in response.freshness:
        count_str = f"{item.count:,}" if item.count else "0"

        if item.status == "stale":
            status_str = f"[yellow]⚠ {item.days_behind}d behind[/yellow]"
        elif item.status == "today":
            status_str = "[green]✓ today[/green]"
        elif item.status == "yesterday":
            status_str = "[green]✓ yesterday[/green]"
        elif item.status == "current":
            status_str = "[green]✓ current[/green]"
        else:
            status_str = "[bright_black]—[/bright_black]"

        freshness_table.add_row(
            item.table, item.source, item.latest, count_str, status_str
        )

    console.print(freshness_table)
