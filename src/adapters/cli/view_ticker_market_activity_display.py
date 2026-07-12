"""
Candles, seasonality, and IEV / pre-open panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _fmt_vol, _not_cached


def _candles_panel(candles: list) -> object:
    if not candles:
        return panel(_not_cached(), title="Recent Candles")

    recent = sorted(candles, key=lambda c: c.date, reverse=True)[:5]

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Open", justify="right")
    tbl.add_column("High", justify="right")
    tbl.add_column("Low", justify="right")
    tbl.add_column("Close", justify="right", style="bold")
    tbl.add_column("Volume", justify="right", style="dim")

    for c in recent:
        tbl.add_row(
            str(c.date),
            f"{c.open:,.0f}",
            f"{c.high:,.0f}",
            f"{c.low:,.0f}",
            f"{c.close:,.0f}",
            _fmt_vol(c.volume),
        )

    return panel(tbl, title="Recent Candles")


def _seasonality_panel(edge, month: int) -> object:
    _MONTH_NAMES = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }
    month_name = _MONTH_NAMES.get(month, str(month))

    if edge is None:
        return panel(_not_cached(), title=f"Seasonality \u2014 {month_name}")

    if edge.is_tailwind:
        edge_label, edge_style = "Tailwind", "green"
    elif edge.is_headwind:
        edge_label, edge_style = "Headwind", "red"
    else:
        edge_label, edge_style = "Neutral", "yellow"

    sign = "+" if edge.avg_monthly_return_pct >= 0 else ""
    lines: list[Text] = [
        Text("  ")
        + Text(edge_label, style=f"bold {edge_style}")
        + Text(
            f"   {sign}{edge.avg_monthly_return_pct:.1f}% avg   {edge.win_rate_pct:.0f}% win-rate",
            style="default",
        ),
        Text(f"  {edge.positive_years} up / {edge.total_years} years of history", style="dim"),
    ]
    return panel(Group(*lines), title=f"Seasonality \u2014 {month_name}")


def _iev_panel(iev_rows: list) -> object:
    if not iev_rows:
        return panel(_not_cached(), title="IEV / Pre-open")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("IEV", justify="right", min_width=10)
    tbl.add_column("Rank", justify="right", min_width=5)
    tbl.add_column("IEP", justify="right", min_width=8)
    tbl.add_column("NCP", min_width=4)

    for row in iev_rows[:5]:
        ncp = Text("\u2713", style="green") if row.is_ncp_locked else Text("\u2014", style="dim")
        tbl.add_row(
            str(row.date),
            _fmt_vol(row.iev),
            f"#{row.rank}",
            f"Rp{row.iep:,}" if row.iep else "\u2014",
            ncp,
        )

    return panel(tbl, title="IEV / Pre-open")
