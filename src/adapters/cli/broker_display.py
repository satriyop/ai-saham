"""
Display helpers for broker CLI output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel


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


def display_broker_flow(ticker: str, summaries: list) -> None:
    console_obj = Console()
    console_obj.print("")
    
    total_flow = sum(summary.foreign_net_value for summary in summaries)
    buy_days = sum(1 for summary in summaries if summary.is_foreign_accumulating)
    sell_days = len(summaries) - buy_days

    consecutive = 0
    for summary in reversed(summaries):
        if summary.is_foreign_accumulating:
            consecutive += 1
        else:
            break

    flow_style = "green" if total_flow > 0 else "red"
    summary_text = Text()
    summary_text.append("Total net flow: ", style="bold")
    summary_text.append(format_value(total_flow), style=f"bold {flow_style}")
    summary_text.append(f" | Buy/Sell days: {buy_days}/{sell_days}")
    summary_text.append(f" | Consecutive buy days: {consecutive}")

    panel_obj = Panel(
        summary_text,
        title=f"[bold]Foreign Flow for {ticker.upper()}[/bold]",
        subtitle=f"last {len(summaries)} trading days",
        border_style="cyan",
        expand=False,
    )
    console_obj.print(panel_obj)
    console_obj.print("")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("Net Flow", justify="right")
    table.add_column("Ratio", justify="right")
    table.add_column("Top Buyer", justify="center")
    table.add_column("Top Seller", justify="center")

    for summary in summaries:
        flow = summary.foreign_net_value
        ratio = summary.foreign_flow_ratio
        color = "green" if flow > 0 else "red"

        top_buyer = summary.top_buyers[0].broker_code if summary.top_buyers else "-"
        top_seller = summary.top_sellers[0].broker_code if summary.top_sellers else "-"

        table.add_row(
            summary.date.isoformat(),
            f"[{color}]{format_value(flow)}[/{color}]",
            f"{ratio:.1f}%",
            top_buyer,
            top_seller,
        )
    console_obj.print(table)


def display_broker_top(ticker: str, summary) -> None:
    console_obj = Console()
    console_obj.print("")

    flow = summary.foreign_net_value
    flow_color = "green" if flow > 0 else "red"
    
    summary_text = Text()
    summary_text.append("Foreign Net Flow: ", style="bold")
    summary_text.append(f"{format_value(flow)} ({summary.foreign_flow_ratio:.1f}%)", style=f"bold {flow_color}")
    summary_text.append(" | ")
    summary_text.append("Total Value: ", style="bold")
    summary_text.append(format_value(summary.total_value))

    panel_obj = Panel(
        summary_text,
        title=f"[bold]Broker Summary for {ticker.upper()}[/bold]",
        subtitle=f"as of {summary.date}",
        border_style="cyan",
        expand=False,
    )
    console_obj.print(panel_obj)

    # Top Buyers Table
    console_obj.print("\n[bold green]Top Buyers[/bold green]")
    buyers_table = Table(show_header=True, header_style="bold magenta")
    buyers_table.add_column("Code", style="cyan")
    buyers_table.add_column("Name", style="white")
    buyers_table.add_column("Type", justify="center")
    buyers_table.add_column("Net Value", justify="right", style="green")
    buyers_table.add_column("Net Lot", justify="right")

    for buyer in summary.top_buyers[:5]:
        type_str = "Foreign" if buyer.is_foreign else "Local"
        buyers_table.add_row(
            buyer.broker_code,
            buyer.broker_name[:20],
            type_str,
            format_value(buyer.net_value),
            f"{buyer.net_lot:,}",
        )
    console_obj.print(buyers_table)

    # Top Sellers Table
    console_obj.print("\n[bold red]Top Sellers[/bold red]")
    sellers_table = Table(show_header=True, header_style="bold magenta")
    sellers_table.add_column("Code", style="cyan")
    sellers_table.add_column("Name", style="white")
    sellers_table.add_column("Type", justify="center")
    sellers_table.add_column("Net Value", justify="right", style="red")
    sellers_table.add_column("Net Lot", justify="right")

    for seller in summary.top_sellers[:5]:
        type_str = "Foreign" if seller.is_foreign else "Local"
        sellers_table.add_row(
            seller.broker_code,
            seller.broker_name[:20],
            type_str,
            format_value(seller.net_value),
            f"{seller.net_lot:,}",
        )
    console_obj.print(sellers_table)


def display_broker_history(ticker: str, points: list) -> None:
    table = compact_table()
    table.add_column("Date")
    table.add_column("Source")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    table.add_column("Avg Price", justify="right")
    for point in points:
        flow_style = "green" if point.net_val > 0 else "red"
        table.add_row(
            point.date.isoformat(),
            point.source,
            Text(format_value(point.net_val), style=flow_style),
            f"{point.net_lot:,}",
            f"{float(point.avg_price):,.0f}",
        )
    console().print(
        panel(
            table,
            title=f"Cached Foreign Flow History for {ticker.upper()}",
            subtitle=f"last {len(points)} trading days",
        )
    )


def display_broker_top_foreign_snapshots(
    *,
    snapshots: list,
    query_date: date,
    days: int,
) -> None:
    table = compact_table()
    table.add_column("#", justify="right")
    table.add_column("Ticker", style="bold")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    table.add_column("Direction")
    for rank, snap in enumerate(snapshots, 1):
        direction = "BUY" if snap.is_accumulating else "SELL"
        flow_style = "green" if snap.is_accumulating else "red"
        table.add_row(
            str(rank),
            snap.ticker,
            Text(format_value(snap.net_val), style=flow_style),
            f"{snap.net_lot:,}",
            Text(direction, style=flow_style),
        )
    console().print(
        panel(
            Group(table),
            title="Cached Foreign Broker Top Stocks",
            subtitle=f"{query_date.isoformat()} / {days} days",
        )
    )


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
