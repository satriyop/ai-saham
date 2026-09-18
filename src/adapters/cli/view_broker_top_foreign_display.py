"""
Display helpers for view broker top-foreign (universe scan cache).

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.shared.view_number_format import format_value


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
