"""
Display helpers for swing CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.market_regime import MarketRegimeResponse
from src.application.use_case.swing_backtest import SwingBacktestResponse


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


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
        ret_str = f"[{ret_color}]{_fmt_pct(ret_val, True)}[/]"
        
        dd_val = response.max_drawdown_pct
        dd_str = f"[red]{_fmt_pct(dd_val, True)}[/]" if dd_val is not None else "N/A"
        
        win_val = response.win_rate_pct
        win_color = "green" if (win_val or 0) >= 55.0 else ("yellow" if (win_val or 0) >= 45.0 else "red")
        win_str = f"[{win_color}]{_fmt_pct(win_val)}[/]" if win_val is not None else "N/A"

        compare_table.add_row(
            name,
            regime_label,
            str(response.trade_count),
            ret_str,
            dd_str,
            win_str,
            profit_factor,
            str(response.skipped_by_regime),
            _fmt_pct(response.exposure_pct)
        )

    console().print(compare_table)
    console().print(Text("\nDISCLAIMER: Historical simulation only. Not trading advice.", style="dim italic"))
    console().print("")


def display_swing_backtest(response: SwingBacktestResponse, show_trades: int) -> None:
    # Summary panel
    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")
    
    summary_table.add_row("Preset Strategy", response.preset)
    summary_table.add_row("Period", f"{response.start_date} to {response.end_date}")
    summary_table.add_row("Transaction Cost", f"{float(response.cost_bps):g} bps one-way (applied on entry & exit)")
    summary_table.add_row("Simulation Logic", "Scans each replay date, opens eligible signals within portfolio limits, then exits by TP/SL/max-hold.")

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
    win_color = "green" if (win_val or 0) >= 55.0 else ("yellow" if (win_val or 0) >= 45.0 else "red")
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
    skips_info = f"no_cash={response.skipped_no_cash} | duplicate={response.skipped_duplicate} | no_forward_data={response.skipped_no_forward_data} | regime={response.skipped_by_regime}"
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

    # Warnings & Footnotes (Panel 4)
    warnings_list = []
    if response.warnings:
        for warning in response.warnings:
            warnings_list.append(Text(f"• {warning}", style="yellow"))

    footer_elements = []
    if warnings_list:
        footer_elements.extend([Text("Warnings", style="bold yellow"), *warnings_list, Text("")])
    footer_elements.append(Text("DISCLAIMER: Historical simulation only. Not trading advice.", style="dim italic"))

    console().print("")
    console().print(
        panel(
            Group(*footer_elements),
            title="Reference Notes"
        )
    )
    console().print("")


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
