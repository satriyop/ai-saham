"""
Display helpers for desk-centric view broker commands.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.domain.entities.broker_flow import BrokerType


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


def _type_label(broker_type: BrokerType) -> str:
    if broker_type == BrokerType.FOREIGN:
        return "Foreign"
    if broker_type == BrokerType.LOCAL:
        return "Local"
    return "—"


def format_desk_show_text(result) -> str:
    """Plain-text desk show for TUI (same facts as CLI display_desk_show)."""
    lines = [
        f"Broker Desk · {result.broker_code} ({result.broker_name})",
        f"type {_type_label(result.broker_type)} · as of {result.as_of}",
        (
            f"Day net {format_value(result.day_net_value)} · "
            f"lot {result.day_net_lot:,} · tickers {result.day_ticker_count}"
        ),
        str(result.scope_note),
        "",
        "Top buy stocks",
    ]
    for row in result.top_buy_stocks or ():
        lines.append(f"  {row.ticker:6}  {format_value(row.net_value):>10}  lot {row.net_lot:,}")
    if not result.top_buy_stocks:
        lines.append("  —")
    lines.append("")
    lines.append("Top sell stocks")
    for row in result.top_sell_stocks or ():
        lines.append(f"  {row.ticker:6}  {format_value(row.net_value):>10}  lot {row.net_lot:,}")
    if not result.top_sell_stocks:
        lines.append("  —")
    lines.append("")
    lines.append("CLI: saham view broker show|top-stocks|flow|history " + result.broker_code)
    return "\n".join(lines)


def format_broker_list_text(desks: list[dict]) -> str:
    """Plain-text tracked desk list for TUI / capture."""
    lines = [
        "Tracked broker desks (broker_daily_flow)",
        "same job as: saham view broker list",
        "",
        f"{'Code':4}  Type",
        "-" * 20,
    ]
    for row in desks:
        lines.append(f"{row['code']:4}  {row['type']}")
    lines.append("-" * 20)
    lines.append("Enter a row to open desk show · esc back")
    return "\n".join(lines)


def display_desk_show(result) -> None:
    c = Console()
    c.print("")
    net_style = "green" if result.day_net_value > 0 else "red"
    header = Text()
    header.append(f"{result.broker_code} ", style="bold cyan")
    header.append(f"({result.broker_name}) · ")
    header.append(_type_label(result.broker_type), style="bold")
    header.append(f" · as of {result.as_of}")
    header.append("\n")
    header.append("Day net: ", style="bold")
    header.append(format_value(result.day_net_value), style=f"bold {net_style}")
    header.append(f" · lot {result.day_net_lot:,} · tickers {result.day_ticker_count}")
    header.append("\n")
    header.append(result.scope_note, style="yellow")
    c.print(Panel(header, title="[bold]Broker Desk[/bold]", border_style="cyan", expand=False))

    _print_stock_side(c, "Top buy stocks", result.top_buy_stocks, "green")
    _print_stock_side(c, "Top sell stocks", result.top_sell_stocks, "red")


def display_desk_top_stocks(result) -> None:
    c = Console()
    c.print("")
    header = Text()
    header.append(f"{result.broker_code} ", style="bold cyan")
    header.append(f"({result.broker_name}) · {_type_label(result.broker_type)}")
    header.append(f" · {result.date}")
    header.append("\n")
    header.append(result.scope_note, style="yellow")
    c.print(
        Panel(
            header,
            title="[bold]Desk Top Stocks[/bold]",
            border_style="cyan",
            expand=False,
        )
    )
    _print_stock_side(c, "Net buy (desk)", result.top_buy_stocks, "green")
    _print_stock_side(c, "Net sell (desk)", result.top_sell_stocks, "red")


def _print_stock_side(c: Console, title: str, rows, color: str) -> None:
    c.print(f"\n[bold {color}]{title}[/bold {color}]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Ticker", style="cyan")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    for row in rows:
        style = "green" if row.net_value > 0 else "red"
        table.add_row(
            row.ticker,
            f"[{style}]{format_value(row.net_value)}[/{style}]",
            f"{row.net_lot:,}",
        )
    c.print(table)


def display_desk_flow(result) -> None:
    c = Console()
    c.print("")
    header = Text()
    header.append(f"{result.broker_code} ", style="bold cyan")
    header.append(f"({result.broker_name}) · {_type_label(result.broker_type)}")
    header.append("\n")
    header.append(result.scope_note, style="yellow")
    c.print(Panel(header, title="[bold]Desk Flow by Day[/bold]", border_style="cyan", expand=False))
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    table.add_column("Tickers", justify="right")
    for day in result.days:
        style = "green" if day.net_value > 0 else "red"
        table.add_row(
            day.date.isoformat(),
            f"[{style}]{format_value(day.net_value)}[/{style}]",
            f"{day.net_lot:,}",
            str(day.ticker_count),
        )
    c.print(table)


def display_desk_history(result) -> None:
    c = Console()
    c.print("")
    pin = f" · ticker {result.pinned_ticker}" if result.pinned_ticker else ""
    header = Text()
    header.append(f"{result.broker_code} ", style="bold cyan")
    header.append(f"({result.broker_name}) · {_type_label(result.broker_type)}{pin}")
    header.append("\n")
    header.append(result.scope_note, style="yellow")
    c.print(Panel(header, title="[bold]Desk History[/bold]", border_style="cyan", expand=False))
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("Ticker")
    table.add_column("Net Value", justify="right")
    table.add_column("Net Lot", justify="right")
    table.add_column("Buy Val", justify="right")
    table.add_column("Sell Val", justify="right")
    for flow in result.flows:
        style = "green" if flow.net_value > 0 else "red"
        table.add_row(
            flow.date.isoformat(),
            flow.ticker,
            f"[{style}]{format_value(flow.net_value)}[/{style}]",
            f"{flow.net_lot:,}",
            format_value(flow.buy_value),
            format_value(flow.sell_value),
        )
    c.print(table)
