"""
Display helpers for view ticker flow (foreign summary table).

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def format_value(value: Decimal) -> str:
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


def display_ticker_flow_table(ticker: str, summaries: list) -> None:
    """Render multi-day foreign flow summary table for a stock."""
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
