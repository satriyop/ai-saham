"""
Candles, price structure, seasonality, and IEV / pre-open panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _fmt_vol, _not_cached, _pct
from src.adapters.cli.view_ticker_price_structure import PriceStructure


def _change_text(value: float | None) -> Text:
    if value is None:
        return Text("\u2014", style="dim")
    style = "green" if value > 0 else ("red" if value < 0 else "default")
    return Text(f"{value:+.1f}%", style=style)


def _price_structure_panel(
    structure: PriceStructure | None,
    *,
    empty_hint: str | None = None,
) -> object:
    """Market structure: multi-horizon change, 52w position, volume vs avg."""
    if structure is None:
        return panel(_not_cached(hint=empty_hint), title="Price Structure")

    lines: list[Text] = []
    lines.append(
        Text("  Close ", style="dim")
        + Text(f"Rp{structure.close:,.0f}", style="bold")
        + Text(f"   as of {structure.as_of}", style="dim")
    )
    lines.append(
        Text("  Chg 1d ", style="dim")
        + _change_text(structure.change_1d_pct)
        + Text("   5d ", style="dim")
        + _change_text(structure.change_5d_pct)
        + Text("   20d ", style="dim")
        + _change_text(structure.change_20d_pct)
    )

    if structure.low_52w is not None and structure.high_52w is not None:
        range_txt = (
            f"  52w  Rp{structure.low_52w:,.0f} \u2013 Rp{structure.high_52w:,.0f}"
        )
        if structure.range_52w_pct is not None:
            range_txt += f"   pos {_pct(structure.range_52w_pct)}"
        lines.append(Text(range_txt, style="default"))

    if structure.volume is not None:
        vol_line = Text("  Vol ", style="dim") + Text(
            _fmt_vol(structure.volume), style="default"
        )
        if structure.avg_volume_20d is not None:
            vol_line += Text(
                f"   20d avg {_fmt_vol(int(structure.avg_volume_20d))}",
                style="dim",
            )
        if structure.volume_vs_20d is not None:
            vs = structure.volume_vs_20d
            vs_style = "green" if vs >= 1.2 else ("red" if vs <= 0.8 else "default")
            vol_line += Text(f"   {vs:.2f}x avg", style=vs_style)
        lines.append(vol_line)

    return panel(Group(*lines), title="Price Structure")


def _candles_panel(candles: list, *, empty_hint: str | None = None) -> object:
    if not candles:
        return panel(_not_cached(hint=empty_hint), title="Recent Candles")

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


def _seasonality_panel(edge, month: int, *, empty_hint: str | None = None) -> object:
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
        return panel(
            _not_cached(hint=empty_hint),
            title=f"Seasonality \u2014 {month_name}",
        )

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


def _iev_panel(iev_rows: list, *, empty_hint: str | None = None) -> object:
    if not iev_rows:
        return panel(_not_cached(hint=empty_hint), title="IEV / Pre-open")

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
