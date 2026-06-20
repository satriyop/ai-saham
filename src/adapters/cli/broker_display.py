"""
Display helpers for broker CLI output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import typer
from rich.console import Group
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
    typer.echo(f"\nTotal foreign net flow: {format_value(total_foreign_flow)}")

    typer.echo("\nRecent foreign flow:")
    for summary in summaries[-5:]:
        flow = summary.foreign_net_value
        color = typer.colors.GREEN if flow > 0 else typer.colors.RED
        typer.echo(
            f"  {summary.date}: "
            + typer.style(format_value(flow), fg=color)
        )


def display_broker_flow(ticker: str, summaries: list) -> None:
    typer.echo(f"\nForeign Flow for {ticker.upper()} (last {len(summaries)} trading days)")
    typer.echo("=" * 60)

    total_flow = sum(summary.foreign_net_value for summary in summaries)
    buy_days = sum(1 for summary in summaries if summary.is_foreign_accumulating)
    sell_days = len(summaries) - buy_days

    consecutive = 0
    for summary in reversed(summaries):
        if summary.is_foreign_accumulating:
            consecutive += 1
        else:
            break

    typer.echo(f"Total net flow: {format_value(total_flow)}")
    typer.echo(f"Buy days: {buy_days} | Sell days: {sell_days}")
    typer.echo(f"Consecutive buy days: {consecutive}")
    typer.echo("-" * 60)

    typer.echo(f"{'Date':<12} {'Net Flow':>12} {'Ratio':>8} {'Top Buyer':>10} {'Top Seller':>10}")
    typer.echo("-" * 60)

    for summary in summaries:
        flow = summary.foreign_net_value
        ratio = summary.foreign_flow_ratio
        color = typer.colors.GREEN if flow > 0 else typer.colors.RED

        top_buyer = summary.top_buyers[0].broker_code if summary.top_buyers else "-"
        top_seller = summary.top_sellers[0].broker_code if summary.top_sellers else "-"

        typer.echo(
            f"{summary.date.isoformat():<12} "
            + typer.style(f"{format_value(flow):>12}", fg=color)
            + f" {ratio:>7.1f}%"
            + f" {top_buyer:>10}"
            + f" {top_seller:>10}"
        )


def display_broker_top(ticker: str, summary) -> None:
    typer.echo(f"\nBroker Summary for {ticker.upper()} on {summary.date}")
    typer.echo("=" * 70)

    flow = summary.foreign_net_value
    color = typer.colors.GREEN if flow > 0 else typer.colors.RED
    typer.echo(
        f"Foreign Net Flow: "
        + typer.style(format_value(flow), fg=color)
        + f" ({summary.foreign_flow_ratio:.1f}%)"
    )
    typer.echo(f"Total Value: {format_value(summary.total_value)}")
    typer.echo("-" * 70)

    typer.echo("\nTop Buyers:")
    typer.echo(f"{'Code':<6} {'Name':<20} {'Type':<8} {'Net Value':>14} {'Net Lot':>10}")
    for buyer in summary.top_buyers[:5]:
        type_str = "Foreign" if buyer.is_foreign else "Local"
        typer.echo(
            f"{buyer.broker_code:<6} "
            f"{buyer.broker_name[:20]:<20} "
            f"{type_str:<8} "
            + typer.style(f"{format_value(buyer.net_value):>14}", fg=typer.colors.GREEN)
            + f" {buyer.net_lot:>10,}"
        )

    typer.echo("\nTop Sellers:")
    typer.echo(f"{'Code':<6} {'Name':<20} {'Type':<8} {'Net Value':>14} {'Net Lot':>10}")
    for seller in summary.top_sellers[:5]:
        type_str = "Foreign" if seller.is_foreign else "Local"
        typer.echo(
            f"{seller.broker_code:<6} "
            f"{seller.broker_name[:20]:<20} "
            f"{type_str:<8} "
            + typer.style(f"{format_value(seller.net_value):>14}", fg=typer.colors.RED)
            + f" {seller.net_lot:>10,}"
        )


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
    typer.echo(f"  {'#':<4} {'TICKER':<8} {'NET VALUE':>14}  {'NET LOT':>10}  DIR")
    typer.echo("  " + "─" * 45)
    for rank, snap in enumerate(snapshots, 1):
        direction = "▲ BUY " if snap.is_accumulating else "▼ SELL"
        color = typer.colors.GREEN if snap.is_accumulating else typer.colors.RED
        line = (
            f"  {rank:<4} {snap.ticker:<8} "
            f"{format_value(snap.net_val):>14}  {snap.net_lot:>10,}  {direction}"
        )
        typer.echo(typer.style(line, fg=color) if rank <= 5 else line)


def display_history_fetch_preview(ticker: str, points: list) -> None:
    recent = sorted(points, key=lambda p: p.date, reverse=True)[:5]
    typer.echo(f"\n  {'DATE':<12} {'NET VALUE':>14}  {'NET LOT':>10}  {'AVG PRICE':>10}")
    typer.echo("  " + "─" * 52)
    for point in recent:
        direction_color = typer.colors.GREEN if point.net_val > 0 else typer.colors.RED
        line = (
            f"  {point.date.isoformat():<12} "
            f"{format_value(point.net_val):>14}  {point.net_lot:>10,}  {float(point.avg_price):>10,.0f}"
        )
        typer.echo(typer.style(line, fg=direction_color))


def display_import_preview(response) -> None:
    typer.echo("\n" + typer.style("Preview Results", bold=True))
    typer.echo("-" * 60)

    if response.summaries:
        typer.echo(f"{'Date':<12} {'Ticker':<8} {'Foreign Net':>14} {'Total Value':>14}")
        typer.echo("-" * 60)

        for summary in response.summaries:
            flow = summary.foreign_net_value
            color = typer.colors.GREEN if flow > 0 else typer.colors.RED
            typer.echo(
                f"{summary.date.isoformat():<12} "
                f"{summary.ticker:<8} "
                + typer.style(f"{format_value(flow):>14}", fg=color)
                + f" {format_value(summary.total_value):>14}"
            )

        typer.echo("-" * 60)
        typer.echo(
            f"Showing {len(response.summaries)} of {response.total_rows} rows"
        )

    if response.errors:
        typer.echo(
            f"\n{typer.style('Errors:', fg=typer.colors.YELLOW)} "
            f"{len(response.errors)} rows with issues"
        )
        for error in response.errors[:3]:
            typer.echo(f"  - {error}")
        if len(response.errors) > 3:
            typer.echo(f"  ... and {len(response.errors) - 3} more")

    typer.echo("\nRun without --preview to import data.")
