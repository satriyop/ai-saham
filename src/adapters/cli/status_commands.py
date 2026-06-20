"""
Data provider health and freshness commands.

Layer: Adapter
"""

import re
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


def _display_width(s: str) -> int:
    """Calculate visual display width of a string, treating common unicode symbols as double-width."""
    # Strip ANSI escape codes first to get clean raw text
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    raw_text = ansi_escape.sub("", s)

    width = 0
    for char in raw_text:
        # Check standard double-width characters used in status output
        if char in ("✓", "⚠", "✅", "✗"):
            width += 2
        else:
            width += 1
    return width


def _pad_visual(text: str, width: int, align: str = "<") -> str:
    """Pad a string to a target visual width, ignoring ANSI escape codes and accounting for double-width chars."""
    dw = _display_width(text)
    padding = max(0, width - dw)
    if align == "<":
        return text + (" " * padding)
    elif align == ">":
        return (" " * padding) + text
    else:
        # center
        left = padding // 2
        right = padding - left
        return (" " * left) + text + (" " * right)


def _health_line(dto: ProviderStatusDto) -> str:
    """Format a health check line with perfect alignment."""
    warning = "key" in dto.label or "expired" in dto.label
    icon = _ICON_OK if dto.ok else (_ICON_WARN if warning else _ICON_FAIL)
    ms_str = f"{dto.ms}s" if dto.ms else ""

    name_col = _pad_visual(dto.name, 18)
    label_col = _pad_visual(dto.label, 52)
    ms_col = _pad_visual(ms_str, 6, align=">")

    return f"  │ {name_col} {icon}  {label_col} {ms_col} │"


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

    # The inner visual width of the health line is 83 cells.
    # Therefore, content_width (dashes inside the top box) is 83.
    content_width = 83

    typer.echo("")
    typer.echo("  ╭─ Data Provider Health " + "─" * (content_width - 23) + "╮")
    for provider_status in response.providers:
        typer.echo(_health_line(provider_status))
    typer.echo("  ╰" + "─" * content_width + "╯")
    typer.echo("")

    _show_data_freshness(db_path, response.freshness)


def _show_data_freshness(db_path: Path, freshness_items: list[FreshnessItem]) -> None:
    """Display data freshness table."""
    # Columns: TABLE (22), SOURCE (12), LATEST (14), ROWS (8), STATUS (16)
    # Spacing: 1 (space) + 1 (space) + 1 (space) + 2 (spaces) = 5 spaces
    # Inner visual width is 22+12+14+8+16+5 = 77 cells.
    # Total visual width with borders: 4 (left) + 77 (inner) + 2 (right) = 83 cells.
    content_width = 77

    if not db_path.exists():
        typer.echo("  ╭─ Data Freshness " + "─" * (content_width - 17) + "╮")
        line1 = f"  │  No database at {db_path}"
        typer.echo(_pad_visual(line1, 81) + " │")
        line2 = "  │  Run: saham fetch market <TICKER>"
        typer.echo(_pad_visual(line2, 81) + " │")
        typer.echo("  ╰" + "─" * content_width + "╯")
        return

    if not freshness_items:
        typer.echo("  No data found.")
        return

    _print_freshness_table(freshness_items)


def _print_freshness_table(items: list[FreshnessItem]) -> None:
    """Print a formatted freshness table with age warnings."""
    content_width = 77

    typer.echo("  ╭─ Data Freshness " + "─" * (content_width - 17) + "╮")

    tbl_hdr = _pad_visual("TABLE", 22)
    src_hdr = _pad_visual("SOURCE", 12)
    lat_hdr = _pad_visual("LATEST", 14)
    rows_hdr = _pad_visual("ROWS", 8, align=">")
    status_hdr = _pad_visual("STATUS", 16)

    typer.echo(
        f"  │ {tbl_hdr} {src_hdr} {lat_hdr} {rows_hdr}  {status_hdr} │"
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

        tbl_col = _pad_visual(item.table, 22)
        src_col = _pad_visual(item.source, 12)
        lat_col = _pad_visual(item.latest, 14)
        rows_col = _pad_visual(count_str, 8, align=">")
        status_col = _pad_visual(styled_text, 16)

        typer.echo(
            f"  │ {tbl_col} {src_col} {lat_col} {rows_col}  {status_col} │"
        )

    typer.echo("  ╰" + "─" * content_width + "╯")
