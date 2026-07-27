"""
Display helpers for saham trade backtest-swing command.

Facade that orchestrates backtest summary, trades, regime performance,
and delegates attribution display to its dedicated module.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.policy_accum_attribution_display import display_swing_attribution
from src.adapters.cli.policy_accum_display_formatters import _fmt_pct
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def display_swing_backtest(
    response: SwingBacktestResponse,
    show_trades: int,
    show_attribution: bool = False,
) -> None:
    # Summary panel
    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")

    summary_table.add_row("Setup", response.setup)
    summary_table.add_row("Period", f"{response.start_date} to {response.end_date}")
    summary_table.add_row(
        "Transaction Cost",
        f"{float(response.cost_bps):g} bps one-way (applied on entry & exit)",
    )
    summary_table.add_row(
        "Simulation Logic",
        (
            "Scans each replay date, opens eligible signals within portfolio "
            "limits, then exits by TP/SL/max-hold."
        ),
    )

    console().print("")
    console().print(
        panel(
            summary_table,
            title="WALK-FORWARD SWING BACKTEST",
        )
    )

    # Core performance metrics table
    metrics_table = compact_table()
    metrics_table.add_column("Performance Metric", style="bold yellow")
    metrics_table.add_column("Value", justify="right")

    metrics_table.add_row("Initial capital", f"{float(response.initial_capital):,.0f} IDR")
    metrics_table.add_row("Final equity", f"{float(response.final_equity):,.0f} IDR")

    ret_val = response.total_return_pct
    ret_color = "green" if (ret_val or 0) >= 0 else "red"
    metrics_table.add_row("Total return", f"[{ret_color}]{_fmt_pct(ret_val, True)}[/]")

    dd_val = response.max_drawdown_pct
    metrics_table.add_row("Max drawdown", f"[red]{_fmt_pct(dd_val, True)}[/]")
    metrics_table.add_row("Trades count", str(response.trade_count))

    win_val = response.win_rate_pct
    win_color = (
        "green"
        if (win_val or 0) >= 55.0
        else "yellow"
        if (win_val or 0) >= 45.0
        else "red"
    )
    metrics_table.add_row("Win rate", f"[{win_color}]{_fmt_pct(win_val)}[/]")
    metrics_table.add_row("Avg trade return", _fmt_pct(response.avg_trade_return_pct, True))

    profit_factor = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    metrics_table.add_row("Profit factor", profit_factor)
    metrics_table.add_row("Exposure days ratio", _fmt_pct(response.exposure_pct))

    # Skips row
    skips_info = (
        f"no_cash={response.skipped_no_cash} | "
        f"duplicate={response.skipped_duplicate} | "
        f"no_forward_data={response.skipped_no_forward_data} | "
        f"regime={response.skipped_by_regime}"
    )
    metrics_table.add_row("Skipped orders count", skips_info)

    console().print(metrics_table)

    # Regime Performance (Panel 2)
    if response.regime_stats:
        regime_table = compact_table()
        regime_table.add_column("Regime", style="bold cyan")
        regime_table.add_column("Trades", justify="right")
        regime_table.add_column("Avg Return", justify="right")
        regime_table.add_column("Win Rate", justify="right")
        regime_table.add_column("Total PnL (IDR)", justify="right")

        for stat in response.regime_stats:
            pnl_color = "green" if stat.total_pnl >= 0 else "red"
            regime_table.add_row(
                stat.regime,
                str(stat.count),
                f"[{pnl_color}]{_fmt_pct(stat.avg_return_pct, True)}[/]",
                _fmt_pct(stat.win_rate_pct),
                f"[{pnl_color}]{float(stat.total_pnl):+,.0f}[/]"
            )
        console().print("")
        console().print(
            panel(
                regime_table,
                title="PERFORMANCE BY ENTRY REGIME",
            )
        )

    # Recent Trades (Panel 3)
    if show_trades > 0 and response.trades:
        trades_table = compact_table()
        trades_table.add_column("Entry Date")
        trades_table.add_column("Exit Date")
        trades_table.add_column("Ticker", style="bold")
        trades_table.add_column("Lots", justify="right")
        trades_table.add_column("Return", justify="right")
        trades_table.add_column("PnL (IDR)", justify="right")
        trades_table.add_column("Days", justify="right")
        trades_table.add_column("Exit Reason")

        for trade in response.trades[-show_trades:]:
            pnl_color = "green" if trade.pnl >= 0 else "red"
            trades_table.add_row(
                f"{trade.entry_date:%Y-%m-%d}",
                f"{trade.exit_date:%Y-%m-%d}",
                trade.ticker,
                str(trade.lots),
                f"[{pnl_color}]{_fmt_pct(trade.net_return_pct, True)}[/]",
                f"[{pnl_color}]{float(trade.pnl):+,.0f}[/]",
                str(trade.holding_days),
                trade.exit_reason
            )
        console().print("")
        console().print(
            panel(
                trades_table,
                title=f"RECENT {len(response.trades[-show_trades:])} TRADES",
            )
        )

    # Attribution (delegated)
    if show_attribution:
        display_swing_attribution(response)

    # Warnings & Footnotes (Panel 4)
    warnings_list = []
    if response.warnings:
        for warning in response.warnings:
            warnings_list.append(Text(f"• {warning}", style="yellow"))

    footer_elements = []
    if warnings_list:
        footer_elements.extend([Text("Warnings", style="bold yellow"), *warnings_list, Text("")])
    footer_elements.append(
        Text(
            "DISCLAIMER: Historical simulation only. Not trading advice.",
            style="dim italic",
        )
    )

    console().print("")
    console().print(
        panel(
            Group(*footer_elements),
            title="Reference Notes"
        )
    )
    console().print("")
