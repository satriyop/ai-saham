"""
Display helpers for `saham view universe`.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.view_universe_summary import (
    UniverseTickerRow,
    UniverseViewResult,
)

def display_universe_view(
    result: UniverseViewResult,
    sort_by: str = "flow",
    top_n: int | None = None,
) -> None:
    """Render a universe market overview table to stdout."""
    c = console()

    sorted_rows = sorted(result.rows, key=lambda r: _sort_key(r, sort_by))
    display_rows = sorted_rows[:top_n] if top_n else sorted_rows
    truncated = len(sorted_rows) - len(display_rows)

    gainers = losers = 0
    total_fnet = Decimal(0)
    for r in result.rows:
        if r.change_pct is not None:
            if r.change_pct > 0:
                gainers += 1
            elif r.change_pct < 0:
                losers += 1
        if r.foreign_net_value is not None:
            total_fnet += r.foreign_net_value

    date_str = result.as_of_date.isoformat() if result.as_of_date else "no data"

    # --- header summary panel ---
    header = compact_table(show_header=False)
    header.add_column("Key", style="bold cyan", width=18)
    header.add_column("Value")
    header.add_row("Universe", result.universe_name.upper())
    header.add_row("Tickers", str(result.ticker_count))
    header.add_row("As of Date", date_str)
    header.add_row("Config Updated", result.updated)
    header.add_row(
        "Gainers / Losers",
        Text.assemble(
            Text(f"{gainers}↑", style="green"),
            "  ",
            Text(f"{losers}↓", style="red"),
        ),
    )
    header.add_row("Total Foreign Net", _fmt_net(total_fnet))
    c.print()
    c.print(panel(header, title=f"UNIVERSE: {result.universe_name.upper()}"))

    # --- main table ---
    tbl = compact_table()
    tbl.add_column("TICKER", style="bold cyan", width=7)
    tbl.add_column("SECTOR", width=20)
    tbl.add_column("CLOSE", justify="right", width=9)
    tbl.add_column("CHG%", justify="right", width=8)
    tbl.add_column("VOL", justify="right", width=8)
    tbl.add_column("F.NET", justify="right", width=10)
    tbl.add_column("FLOW%", justify="right", width=7)

    for row in display_rows:
        sector_short = (row.sector or "—")[:19]
        tbl.add_row(
            row.ticker,
            sector_short,
            _fmt_price(row.last_close),
            _fmt_pct(row.change_pct),
            _fmt_volume(row.volume),
            _fmt_net(row.foreign_net_value),
            _fmt_flow_ratio(row.foreign_flow_ratio),
        )

    c.print(tbl)

    if truncated:
        c.print(f"  … {truncated} more rows (raise --top or omit for all)")

    if result.missing_flow > 0:
        c.print(
            f"\n  [yellow]⚠ {result.missing_flow} ticker(s) have no flow data[/yellow]"
            f" — run: [bold]saham fetch market --universe {result.universe_name}[/bold]"
        )
    if result.missing_candles > 0:
        c.print(
            f"  [yellow]⚠ {result.missing_candles} ticker(s) have no price data[/yellow]"
            f" — run: [bold]saham fetch market --universe {result.universe_name}[/bold]"
        )
    c.print()


def display_universe_list(meta: dict) -> None:
    """Render a compact list of all configured universes."""
    c = console()
    tbl = compact_table()
    tbl.add_column("UNIVERSE", style="bold cyan", width=16)
    tbl.add_column("TICKERS", justify="right", width=8)
    tbl.add_column("LAST UPDATED", width=14)
    for name, info in sorted(meta.items()):
        tbl.add_row(name, str(info["count"]), str(info["updated"]))
    c.print()
    c.print(panel(tbl, title="CONFIGURED UNIVERSES"))
    c.print("  Usage: [bold]saham view universe <name>[/bold]  (e.g. lq45, bank, finance)")
    c.print()


# ---------------------------------------------------------------------------
# Sort key
# ---------------------------------------------------------------------------

def _sort_key(row: UniverseTickerRow, sort_by: str):
    """Nulls-last sort key; secondary sort by change_pct desc for flow ties."""
    if sort_by == "flow":
        ratio = row.foreign_flow_ratio
        change = row.change_pct if row.change_pct is not None else -999.0
        return (ratio is None, -(ratio or 0.0), -change)
    if sort_by == "change":
        pct = row.change_pct
        return (pct is None, -(pct or 0.0))
    if sort_by == "volume":
        vol = row.volume
        return (vol is None, -(vol or 0))
    return (row.ticker,)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_price(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _fmt_pct(value: float | None) -> Text:
    if value is None:
        return Text("—", style="bright_black")
    sign = "+" if value >= 0 else ""
    style = "green" if value > 0 else "red" if value < 0 else "white"
    return Text(f"{sign}{value:.2f}%", style=style)


def _fmt_volume(volume: int | None) -> str:
    if volume is None:
        return "—"
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f}M"
    if volume >= 1_000:
        return f"{volume / 1_000:.0f}K"
    return str(volume)


def _fmt_net(value: Decimal | None) -> Text:
    if value is None:
        return Text("—", style="bright_black")
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        s = f"{sign}{abs_v / 1_000_000_000_000:.2f}T"
    elif abs_v >= 1_000_000_000:
        s = f"{sign}{abs_v / 1_000_000_000:.1f}B"
    elif abs_v >= 1_000_000:
        s = f"{sign}{abs_v / 1_000_000:.0f}M"
    else:
        s = f"{sign}{abs_v:.0f}"
    style = "green" if value > 0 else "red"
    return Text(s, style=style)


def _fmt_flow_ratio(ratio: float | None) -> Text:
    if ratio is None:
        return Text("—", style="bright_black")
    sign = "+" if ratio >= 0 else ""
    style = "green" if ratio > 0 else "red"
    return Text(f"{sign}{ratio:.1f}%", style=style)
