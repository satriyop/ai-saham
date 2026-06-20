"""
Data provider health and freshness commands.

Layer: Adapter
"""

from pathlib import Path

import typer

from src.application.use_case.get_system_status import (
    FreshnessItem,
    GetSystemStatusUseCase,
)
from src.domain.ports.system_status_provider import ProviderStatusDto
from src.infrastructure.persistence.sqlite_system_status_provider import (
    SQLiteSystemStatusProvider,
)

DEFAULT_DB_PATH = Path("data.db")

_ICON_OK = typer.style(" ✅", fg=typer.colors.GREEN, bold=True)
_ICON_WARN = typer.style(" ⚠", fg=typer.colors.YELLOW, bold=True)
_ICON_FAIL = typer.style(" ✗", fg=typer.colors.RED, bold=True)
_W = 80


def _health_line(dto: ProviderStatusDto) -> str:
    """Format a health check line."""
    warning = "key" in dto.label or "expired" in dto.label
    icon = _ICON_OK if dto.ok else (_ICON_WARN if warning else _ICON_FAIL)
    ms_str = f"{dto.ms}s" if dto.ms else ""
    return f"  │ {dto.name:<18s} {icon}  {dto.label:<52s} {ms_str:>6s} │"


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
    content_width = _W - 4

    # Inject dependencies and execute use case
    provider = SQLiteSystemStatusProvider(db_path=db_path)
    use_case = GetSystemStatusUseCase(provider=provider)
    response = use_case.execute()

    typer.echo("")
    typer.echo("  ╭─ Data Provider Health " + "─" * (content_width - 23) + "╮")
    for provider_status in response.providers:
        typer.echo(_health_line(provider_status))
    typer.echo("  ╰" + "─" * content_width + "╯")
    typer.echo("")

    _show_data_freshness(db_path, response.freshness)


def _show_data_freshness(db_path: Path, freshness_items: list[FreshnessItem]) -> None:
    """Display data freshness table."""
    content_width = _W - 4

    if not db_path.exists():
        typer.echo("  ╭─ Data Freshness " + "─" * (content_width - 17) + "╮")
        typer.echo(f"  │  No database at {str(db_path):<{content_width - 7}s} │")
        typer.echo(f"  │  Run: saham fetch market <TICKER>{' ' * (content_width - 35)} │")
        typer.echo("  ╰" + "─" * content_width + "╯")
        return

    if not freshness_items:
        typer.echo("  No data found.")
        return

    _print_freshness_table(freshness_items)


def _print_freshness_table(items: list[FreshnessItem]) -> None:
    """Print a formatted freshness table with age warnings."""
    content_width = _W - 4

    typer.echo("  ╭─ Data Freshness " + "─" * (content_width - 17) + "╮")
    typer.echo(
        f"  │ {'TABLE':<22s} {'SOURCE':<12s} {'LATEST':<14s} "
        f"{'ROWS':>8s}  {'STATUS':<16s} │"
    )
    typer.echo("  │ " + "─" * (content_width - 2) + " │")

    for item in items:
        count_str = f"{item.count:,}" if item.count else "0"

        if item.status == "stale":
            raw_text = f"⚠ {item.days_behind}d behind"
            styled_text = typer.style(raw_text, fg=typer.colors.YELLOW)
        elif item.status == "today":
            raw_text = "✓ today"
            styled_text = typer.style(raw_text, fg=typer.colors.GREEN)
        elif item.status == "yesterday":
            raw_text = "✓ yesterday"
            styled_text = typer.style(raw_text, fg=typer.colors.GREEN)
        elif item.status == "current":
            raw_text = "✓ current"
            styled_text = typer.style(raw_text, fg=typer.colors.GREEN)
        else:
            raw_text = "—"
            styled_text = typer.style(raw_text, fg=typer.colors.BRIGHT_BLACK)

        # Pad manually based on raw text length (excluding ANSI escape codes)
        padding_len = max(0, 16 - len(raw_text))
        status_column = styled_text + (" " * padding_len)

        typer.echo(
            f"  │ {item.table:<22s} {item.source:<12s} "
            f"{item.latest:<14s} {count_str:>8s}  {status_column} │"
        )

    typer.echo("  ╰" + "─" * content_width + "╯")
