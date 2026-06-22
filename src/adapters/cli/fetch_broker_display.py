"""
Display helpers for fetch broker CLI output.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table


def format_value(value: Decimal) -> str:
    """Format large numbers for display (B/M/K)."""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


def display_recent_fetch_summary(summaries: list) -> None:
    if not summaries:
        return
    total_foreign_flow = sum(summary.foreign_net_value for summary in summaries)
    
    console_obj = Console()
    console_obj.print("")
    
    flow_style = "green" if total_foreign_flow > 0 else "red"
    console_obj.print(f"Total foreign net flow: [bold {flow_style}]{format_value(total_foreign_flow)}[/bold {flow_style}]")
    console_obj.print("\nRecent foreign flow:")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("Foreign Net Flow", justify="right")
    
    for summary in summaries[-5:]:
        flow = summary.foreign_net_value
        style = "green" if flow > 0 else "red"
        table.add_row(
            summary.date.isoformat() if hasattr(summary.date, "isoformat") else str(summary.date),
            f"[{style}]{format_value(flow)}[/{style}]",
        )
    console_obj.print(table)


def display_foreign_top_scan(snapshots: list) -> None:
    console_obj = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right")
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    table.add_column("Direction", justify="center")

    for rank, snap in enumerate(snapshots, 1):
        direction = "▲ BUY" if snap.is_accumulating else "▼ SELL"
        color = "green" if snap.is_accumulating else "red"
        
        # Style top 5 rank rows
        style_val = f"[{color}]{format_value(snap.net_val)}[/{color}]" if rank <= 5 else format_value(snap.net_val)
        style_lot = f"[{color}]{snap.net_lot:,}[/{color}]" if rank <= 5 else f"{snap.net_lot:,}"
        style_dir = f"[{color}]{direction}[/{color}]" if rank <= 5 else direction
        
        table.add_row(
            str(rank),
            snap.ticker,
            style_val,
            style_lot,
            style_dir,
        )
    console_obj.print(table)


def display_history_fetch_preview(ticker: str, points: list) -> None:
    console_obj = Console()
    console_obj.print(f"\nRecent Foreign Flow Fetch Preview for [bold cyan]{ticker.upper()}[/bold cyan]:")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    table.add_column("Avg Price", justify="right")

    recent = sorted(points, key=lambda p: p.date, reverse=True)[:5]
    for point in recent:
        color = "green" if point.net_val > 0 else "red"
        table.add_row(
            point.date.isoformat(),
            f"[{color}]{format_value(point.net_val)}[/{color}]",
            f"[{color}]{point.net_lot:,}[/{color}]",
            f"{float(point.avg_price):,.0f}",
        )
    console_obj.print(table)


def display_import_preview(response) -> None:
    console_obj = Console()
    console_obj.print("")
    console_obj.print("[bold]Preview Results[/bold]")

    if response.summaries:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date", style="cyan")
        table.add_column("Ticker", style="cyan bold")
        table.add_column("Foreign Net Value", justify="right")
        table.add_column("Total Value", justify="right")

        for summary in response.summaries:
            flow = summary.foreign_net_value
            color = "green" if flow > 0 else "red"
            table.add_row(
                summary.date.isoformat(),
                summary.ticker,
                f"[{color}]{format_value(flow)}[/{color}]",
                format_value(summary.total_value),
            )
        console_obj.print(table)
        console_obj.print(f"Showing {len(response.summaries)} of {response.total_rows} rows")

    if response.errors:
        console_obj.print(f"\n[yellow]Errors:[/yellow] {len(response.errors)} rows with issues")
        for error in response.errors[:3]:
            console_obj.print(f"  - {error}")
        if len(response.errors) > 3:
            console_obj.print(f"  ... and {len(response.errors) - 3} more")

    console_obj.print("\nRun without --preview to import data.")
