"""
Display helpers for intraday backtest CLI output.

Layer: Adapter
"""

from __future__ import annotations

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.intraday_pre_open_display import fmt_pct
from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.intraday_backtest import IntradayBacktestResponse



def display_intraday_backtest(response: IntradayBacktestResponse, show_trades: int) -> None:
    """Print walk-forward intraday backtest results to the console."""
    # 1. Info Header
    info_table = compact_table(show_header=False)
    info_table.add_column("Key", style="bold cyan")
    info_table.add_column("Value")
    info_table.add_row("Period", f"{response.start_date} to {response.end_date}")
    info_table.add_row(
        "Config",
        f"cost={float(response.cost_bps):g} bps/side | "
        f"max_daily={response.max_daily_positions} | "
        f"include_wait={response.include_wait}"
    )
    info_table.add_row(
        "Entry",
        "candle.open (IDX 09:00 call-auction clearing price)"
    )
    info_table.add_row(
        "Exit",
        "H/L/close same day. Both-breached → stop (conservative)."
    )
    info_table.add_row(
        "IEV",
        "not replayed — all universe tickers screened each day."
    )

    console().print("")
    console().print(
        panel(
            info_table,
            title="INTRADAY WALK-FORWARD BACKTEST (Option A — daily OHLC proxy)",
        )
    )

    # 2. Performance Summary
    metrics_table = compact_table(show_header=False)
    metrics_table.add_column("Metric", style="bold cyan")
    metrics_table.add_column("Value", justify="right")

    metrics_table.add_row("Initial capital", f"{float(response.initial_capital):,.0f}")
    
    equity_color = "green" if response.final_equity >= response.initial_capital else "red"
    metrics_table.add_row("Final equity", f"[{equity_color}]{float(response.final_equity):,.0f}[/]")

    ret_color = "green" if response.total_return_pct >= 0 else "red"
    metrics_table.add_row("Total return", f"[{ret_color}]{fmt_pct(response.total_return_pct, True)}[/]")
    
    metrics_table.add_row("Max drawdown", f"[red]{fmt_pct(response.max_drawdown_pct, True)}[/]")
    metrics_table.add_row("Trades", str(response.trade_count))
    
    win_rate_color = "green" if response.win_rate_pct >= 50 else "red" if response.win_rate_pct < 40 else "white"
    metrics_table.add_row("Win rate", f"[{win_rate_color}]{fmt_pct(response.win_rate_pct)}[/]")

    avg_ret_color = "green" if response.avg_trade_return_pct >= 0 else "red"
    metrics_table.add_row("Avg trade return (net)", f"[{avg_ret_color}]{fmt_pct(response.avg_trade_return_pct, True)}[/]")

    metrics_table.add_row("Avg winner", f"[green]{fmt_pct(response.avg_winner_pct, True)}[/]")
    metrics_table.add_row("Avg loser", f"[red]{fmt_pct(response.avg_loser_pct, True)}[/]")

    if response.profit_factor == float("inf"):
        pf_str = "INF"
        pf_color = "green"
    elif response.profit_factor is None:
        pf_str = "N/A"
        pf_color = "white"
    else:
        pf_str = f"{response.profit_factor:.2f}"
        pf_color = "green" if response.profit_factor >= 1.5 else "red" if response.profit_factor < 1.0 else "white"
    metrics_table.add_row("Profit factor", f"[{pf_color}]{pf_str}[/]")

    if response.expectancy_pct is not None:
        exp_str = fmt_pct(response.expectancy_pct, signed=True)
        exp_color = "green" if response.expectancy_pct >= 0 else "red"
    else:
        exp_str = "N/A"
        exp_color = "white"
    metrics_table.add_row("Expectancy", f"[{exp_color}]{exp_str}[/]")

    r_str = f"{response.avg_r_multiple:.3f}R" if response.avg_r_multiple is not None else "N/A"
    metrics_table.add_row("Avg R-multiple", r_str)
    
    metrics_table.add_row("Trading days", str(response.trading_days))
    metrics_table.add_row("Days with trades", str(response.days_with_trades))

    console().print("")
    console().print(
        panel(
            metrics_table,
            title="PERFORMANCE SUMMARY"
        )
    )

    # 3. Exit Reasons
    if response.exit_reason_counts:
        exit_table = compact_table()
        exit_table.add_column("Reason", style="bold cyan")
        exit_table.add_column("Count", justify="right")
        exit_table.add_column("Percentage", justify="right")
        exit_table.add_column("Flag", style="bold yellow")

        total_trades = response.trade_count
        for reason, count in sorted(response.exit_reason_counts.items(), key=lambda x: -x[1]):
            pct = count / total_trades * 100 if total_trades else 0
            flag = ""
            if reason == "both_assume_stop" and total_trades > 0 and count / total_trades > 0.15:
                flag = "← H/L ambiguity HIGH (>15%)"
            exit_table.add_row(
                reason,
                str(count),
                f"{pct:.0f}%",
                flag
            )

        console().print("")
        console().print(
            panel(
                exit_table,
                title="EXIT REASONS"
            )
        )

    # 4. Breakdowns
    def render_breakdown(title: str, rows: list[dict]) -> None:
        if not rows:
            return
        table = compact_table()
        table.add_column("Label", style="bold cyan")
        table.add_column("Trades", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg Return", justify="right")
        table.add_column("Total PnL (IDR)", justify="right")

        for row in rows:
            pnl = float(row["total_pnl"])
            pnl_color = "green" if pnl >= 0 else "red"
            win_rate = fmt_pct(row["win_rate_pct"])
            avg_return = fmt_pct(row["avg_return_pct"], signed=True)
            table.add_row(
                row["label"],
                str(row["count"]),
                win_rate,
                f"[{pnl_color}]{avg_return}[/]",
                f"[{pnl_color}]{pnl:+,.0f}[/]"
            )
        console().print("")
        console().print(panel(table, title=title))

    render_breakdown("BY ACCUM TAG", response.by_accum_tag)
    render_breakdown("BY FVWAP SIGN", response.by_fvwap_sign)
    render_breakdown("BY RSI BUCKET", response.by_rsi_bucket)
    render_breakdown("TOP TICKERS (by trade count)", response.by_ticker)

    # 5. Recent Trades
    if show_trades > 0 and response.trades:
        display_list = response.trades[-show_trades:]
        trades_table = compact_table()
        trades_table.add_column("Date")
        trades_table.add_column("Ticker", style="bold")
        trades_table.add_column("Dec")
        trades_table.add_column("Open", justify="right")
        trades_table.add_column("Stop", justify="right")
        trades_table.add_column("Target", justify="right")
        trades_table.add_column("Exit", justify="right")
        trades_table.add_column("Exit Reason")
        trades_table.add_column("Return", justify="right")
        trades_table.add_column("PnL (IDR)", justify="right")

        for trade in display_list:
            pnl_val = float(trade.pnl)
            pnl_color = "green" if pnl_val >= 0 else "red"
            ret_col = fmt_pct(trade.net_return_pct, signed=True)
            trades_table.add_row(
                trade.trade_date.isoformat(),
                trade.ticker,
                trade.decision,
                f"{float(trade.entry_price):,.0f}",
                f"{float(trade.stop_price):,.0f}",
                f"{float(trade.target_price):,.0f}",
                f"{float(trade.exit_price):,.0f}",
                trade.exit_reason,
                f"[{pnl_color}]{ret_col}[/]",
                f"[{pnl_color}]{pnl_val:+,.0f}[/]"
            )

        console().print("")
        console().print(
            panel(
                trades_table,
                title=f"RECENT {len(display_list)} TRADES (of {response.trade_count} total)"
            )
        )

    # 6. Warnings & Footer
    warnings_list = []
    for warning in response.warnings:
        prefix = "⚠ " if "WARNING" in warning else "! "
        warnings_list.append(Text(f"• {prefix}{warning}", style="yellow"))

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

