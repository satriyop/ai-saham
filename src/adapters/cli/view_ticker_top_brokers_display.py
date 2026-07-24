"""
Display helpers for view ticker top-brokers.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


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


def _broker_type_label(broker) -> str:
    """Foreign / Local / — (unknown)."""
    from src.domain.entities.broker_flow import BrokerType

    broker_type = getattr(broker, "broker_type", None)
    if broker_type == BrokerType.UNKNOWN:
        return "—"
    if broker_type == BrokerType.FOREIGN:
        return "Foreign"
    if broker_type == BrokerType.LOCAL:
        return "Local"
    return "Foreign" if getattr(broker, "is_foreign", False) else "Local"


def display_ticker_top_brokers(
    ticker: str,
    summary,
    *,
    top_buyers=None,
    top_sellers=None,
    tops_scope_note: str | None = None,
    display_limit: int = 5,
) -> None:
    """Render top broker desks for a stock."""
    console_obj = Console()
    console_obj.print("")

    buyers = list(top_buyers if top_buyers is not None else summary.top_buyers)
    sellers = list(top_sellers if top_sellers is not None else summary.top_sellers)

    flow = summary.foreign_net_value
    flow_color = "green" if flow > 0 else "red"

    summary_text = Text()
    summary_text.append("Foreign Net Flow: ", style="bold")
    summary_text.append(
        f"{format_value(flow)} ({summary.foreign_flow_ratio:.1f}%)",
        style=f"bold {flow_color}",
    )
    summary_text.append(" | ")
    summary_text.append("Total Value: ", style="bold")
    summary_text.append(format_value(summary.total_value))
    if tops_scope_note:
        summary_text.append("\n")
        summary_text.append(tops_scope_note, style="yellow")

    panel_obj = Panel(
        summary_text,
        title=f"[bold]Top Brokers for {ticker.upper()}[/bold]",
        subtitle=f"as of {summary.date}",
        border_style="cyan",
        expand=False,
    )
    console_obj.print(panel_obj)

    buyer_title = "Top Buyers"
    seller_title = "Top Sellers"
    if tops_scope_note:
        buyer_title = "Top Buyers (tracked brokers)"
        seller_title = "Top Sellers (tracked brokers)"

    console_obj.print(f"\n[bold green]{buyer_title}[/bold green]")
    buyers_table = Table(show_header=True, header_style="bold magenta")
    buyers_table.add_column("Code", style="cyan")
    buyers_table.add_column("Name", style="white")
    buyers_table.add_column("Type", justify="center")
    buyers_table.add_column("Net Value", justify="right", style="green")
    buyers_table.add_column("Net Lot", justify="right")

    for buyer in buyers[:display_limit]:
        buyers_table.add_row(
            buyer.broker_code,
            buyer.broker_name[:20],
            _broker_type_label(buyer),
            format_value(buyer.net_value),
            f"{buyer.net_lot:,}",
        )
    console_obj.print(buyers_table)

    console_obj.print(f"\n[bold red]{seller_title}[/bold red]")
    sellers_table = Table(show_header=True, header_style="bold magenta")
    sellers_table.add_column("Code", style="cyan")
    sellers_table.add_column("Name", style="white")
    sellers_table.add_column("Type", justify="center")
    sellers_table.add_column("Net Value", justify="right", style="red")
    sellers_table.add_column("Net Lot", justify="right")

    for seller in sellers[:display_limit]:
        sellers_table.add_row(
            seller.broker_code,
            seller.broker_name[:20],
            _broker_type_label(seller),
            format_value(seller.net_value),
            f"{seller.net_lot:,}",
        )
    console_obj.print(sellers_table)
