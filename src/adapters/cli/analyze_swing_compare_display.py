"""
Swing backtest comparison display for saham analyze swing-compare.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from rich.text import Text

from src.adapters.cli.analyze_swing_formatters import _fmt_pct_compare
from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def display_swing_compare(
    rows: list[tuple[str, SwingBacktestResponse]],
    start_date: date,
    end_date: date,
    universe_label: str,
    variants_by_name: dict[str, tuple[str, ...]],
) -> None:
    # Metadata panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    cost_bps = rows[0][1].cost_bps if rows else Decimal("0")
    meta_table.add_row("Universe", universe_label.upper())
    meta_table.add_row("Period", f"{start_date} to {end_date}")
    meta_table.add_row("Commission Cost", f"{float(cost_bps):g} bps one-way")

    console().print("")
    console().print(
        panel(
            meta_table,
            title="SWING BACKTEST COMPARISON",
        )
    )

    # Comparison Grid
    compare_table = compact_table()
    compare_table.add_column("Variant", style="bold yellow")
    compare_table.add_column("Regimes", style="cyan")
    compare_table.add_column("Trades", justify="right")
    compare_table.add_column("Return", justify="right")
    compare_table.add_column("Max DD", justify="right")
    compare_table.add_column("Win", justify="right")
    compare_table.add_column("PF", justify="right")
    compare_table.add_column("Skip Reg", justify="right")
    compare_table.add_column("Exposure", justify="right")

    for name, response in rows:
        regimes = variants_by_name[name]
        regime_label = "all" if not regimes else ",".join(regimes)
        profit_factor = (
            "INF" if response.profit_factor == float("inf")
            else "N/A" if response.profit_factor is None
            else f"{response.profit_factor:.2f}"
        )

        ret_val = response.total_return_pct
        ret_color = "green" if (ret_val or 0) >= 0 else "red"
        ret_str = f"[{ret_color}]{_fmt_pct_compare(ret_val, True)}[/]"

        dd_val = response.max_drawdown_pct
        dd_str = f"[red]{_fmt_pct_compare(dd_val, True)}[/]" if dd_val is not None else "N/A"

        win_val = response.win_rate_pct
        win_color = "green" if (win_val or 0) >= 55.0 else ("yellow" if (win_val or 0) >= 45.0 else "red")
        win_str = f"[{win_color}]{_fmt_pct_compare(win_val)}[/]" if win_val is not None else "N/A"

        compare_table.add_row(
            name,
            regime_label,
            str(response.trade_count),
            ret_str,
            dd_str,
            win_str,
            profit_factor,
            str(response.skipped_by_regime),
            _fmt_pct_compare(response.exposure_pct)
        )

    console().print(compare_table)
    console().print(Text("\nDISCLAIMER: Historical simulation only. Not trading advice.", style="dim italic"))
    console().print("")
