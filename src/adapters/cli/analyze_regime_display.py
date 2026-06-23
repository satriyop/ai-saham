"""
Display helpers for saham analyze regime command.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.market_regime_use_case import MarketRegimeResponse


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def display_regime(response: MarketRegimeResponse) -> None:
    # Detail table
    regime_table = compact_table(show_header=False)
    regime_table.add_column("Parameter", style="bold cyan")
    regime_table.add_column("Value")

    close = "N/A" if response.benchmark_close is None else f"{float(response.benchmark_close):,.2f}"
    sma20 = "N/A" if response.benchmark_sma20 is None else f"{float(response.benchmark_sma20):,.2f}"
    sma50 = "N/A" if response.benchmark_sma50 is None else f"{float(response.benchmark_sma50):,.2f}"

    regime_table.add_row(f"{response.benchmark_ticker} close", close)
    regime_table.add_row("Benchmark SMA20", sma20)
    regime_table.add_row("Benchmark SMA50", sma50)

    ret_5d = response.benchmark_return_5d_pct
    ret_5d_color = "green" if (ret_5d or 0) >= 0 else "red"
    regime_table.add_row("Benchmark 5d return", f"[{ret_5d_color}]{_fmt_pct(ret_5d, True)}[/]")

    ret_20d = response.benchmark_return_20d_pct
    ret_20d_color = "green" if (ret_20d or 0) >= 0 else "red"
    regime_table.add_row("Benchmark 20d return", f"[{ret_20d_color}]{_fmt_pct(ret_20d, True)}[/]")

    regime_table.add_row("Breadth above SMA20", _fmt_pct(response.breadth_above_sma20_pct))

    change_5d = response.breadth_change_5d_pct
    change_color = "green" if (change_5d or 0) >= 0 else "red"
    regime_table.add_row("Breadth change 5d", f"[{change_color}]{_fmt_pct(change_5d, True)}[/]")

    regime_table.add_row("Foreign flow breadth", _fmt_pct(response.foreign_flow_breadth_pct))
    regime_table.add_row("Universe evaluated", f"{response.breadth_count} / {response.universe_count}")
    regime_table.add_row("Flow evaluated", f"{response.foreign_flow_count} / {response.universe_count}")

    sections = [regime_table]

    if response.warnings:
        warnings_list = []
        for warning in response.warnings:
            warnings_list.append(Text(f"• {warning}", style="yellow"))
        sections.extend([Text("\nWarnings", style="bold yellow"), *warnings_list])

    console().print("")
    console().print(
        panel(
            Group(*sections),
            title="MARKET REGIME",
            subtitle=f"{response.as_of_date.isoformat()} · {response.label} · score: {response.score}/7"
        )
    )
    console().print("")
