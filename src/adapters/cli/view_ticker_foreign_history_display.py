"""
Display helpers for view ticker foreign-history.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel


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


def display_ticker_foreign_history(ticker: str, points: list) -> None:
    """Render foreign_flow_points time series for a stock."""
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
            title=f"Foreign Flow History for {ticker.upper()}",
            subtitle=f"last {len(points)} trading days · foreign net only",
        )
    )
