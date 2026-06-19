"""
Display helpers for intraday backtest CLI output.

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.adapters.cli.intraday_pre_open_display import fmt_pct
from src.application.use_case.intraday_backtest import IntradayBacktestResponse


def display_intraday_backtest(response: IntradayBacktestResponse, show_trades: int) -> None:
    """Print walk-forward intraday backtest results to the console."""
    width = 72
    typer.echo("")
    typer.echo(typer.style("=" * width, fg=typer.colors.CYAN))
    typer.echo(typer.style("INTRADAY WALK-FORWARD BACKTEST (Option A — daily OHLC proxy)", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * width, fg=typer.colors.CYAN))
    typer.echo(f"Period : {response.start_date} to {response.end_date}")
    typer.echo(
        f"Config : cost={float(response.cost_bps):g} bps/side | "
        f"max_daily={response.max_daily_positions} | "
        f"include_wait={response.include_wait}"
    )
    typer.echo(
        "Entry  : candle.open (IDX 09:00 call-auction clearing price)\n"
        "Exit   : H/L/close same day. Both-breached → stop (conservative).\n"
        "IEV    : not replayed — all universe tickers screened each day."
    )
    typer.echo("")

    typer.echo(f"{'METRIC':<30} {'VALUE':>20}")
    typer.echo("-" * 54)
    typer.echo(f"{'Initial capital':<30} {float(response.initial_capital):>20,.0f}")
    typer.echo(f"{'Final equity':<30} {float(response.final_equity):>20,.0f}")
    typer.echo(f"{'Total return':<30} {fmt_pct(response.total_return_pct, True):>20}")
    typer.echo(f"{'Max drawdown':<30} {fmt_pct(response.max_drawdown_pct, True):>20}")
    typer.echo(f"{'Trades':<30} {response.trade_count:>20}")
    typer.echo(f"{'Win rate':<30} {fmt_pct(response.win_rate_pct):>20}")
    typer.echo(f"{'Avg trade return (net)':<30} {fmt_pct(response.avg_trade_return_pct, True):>20}")
    typer.echo(f"{'Avg winner':<30} {fmt_pct(response.avg_winner_pct, True):>20}")
    typer.echo(f"{'Avg loser':<30} {fmt_pct(response.avg_loser_pct, True):>20}")
    pf_str = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    typer.echo(f"{'Profit factor':<30} {pf_str:>20}")
    exp_str = fmt_pct(response.expectancy_pct, signed=True) if response.expectancy_pct is not None else "N/A"
    typer.echo(f"{'Expectancy':<30} {exp_str:>20}")
    r_str = f"{response.avg_r_multiple:.3f}R" if response.avg_r_multiple is not None else "N/A"
    typer.echo(f"{'Avg R-multiple':<30} {r_str:>20}")
    typer.echo(f"{'Trading days':<30} {response.trading_days:>20}")
    typer.echo(f"{'Days with trades':<30} {response.days_with_trades:>20}")
    typer.echo("")

    if response.exit_reason_counts:
        typer.echo("EXIT REASONS")
        total_trades = response.trade_count
        for reason, count in sorted(response.exit_reason_counts.items(), key=lambda x: -x[1]):
            pct = count / total_trades * 100 if total_trades else 0
            flag = ""
            if reason == "both_assume_stop" and total_trades > 0 and count / total_trades > 0.15:
                flag = " ← H/L ambiguity HIGH (>15%)"
            typer.echo(f"  {reason:<22} {count:>5}  ({pct:.0f}%){flag}")
        typer.echo("")

    def print_breakdown(title: str, rows: list[dict]) -> None:
        if not rows:
            return
        typer.echo(title)
        typer.echo(f"  {'LABEL':<22} {'TRADES':>7} {'WIN%':>7} {'AVG_RET':>9} {'TOTAL_PNL':>14}")
        typer.echo("  " + "-" * 63)
        for row in rows:
            pnl = float(row["total_pnl"])
            pnl_str = f"{pnl:+,.0f}"
            win_rate = fmt_pct(row["win_rate_pct"])
            avg_return = fmt_pct(row["avg_return_pct"], signed=True)
            typer.echo(
                f"  {row['label']:<22} {row['count']:>7} "
                f"{win_rate:>7} {avg_return:>9} {pnl_str:>14}"
            )
        typer.echo("")

    print_breakdown("BY ACCUM TAG", response.by_accum_tag)
    print_breakdown("BY FVWAP SIGN", response.by_fvwap_sign)
    print_breakdown("BY RSI BUCKET", response.by_rsi_bucket)
    print_breakdown("TOP TICKERS (by trade count)", response.by_ticker)

    if show_trades > 0 and response.trades:
        display = response.trades[-show_trades:]
        typer.echo(f"RECENT {len(display)} TRADES (of {response.trade_count} total)")
        typer.echo(
            f"  {'DATE':<12} {'TICKER':<6} {'DEC':<6} {'OPEN':>7} "
            f"{'STOP':>7} {'TARGET':>7} {'EXIT':>7} {'REASON':<18} {'RET%':>7} {'PNL':>10}"
        )
        typer.echo("  " + "-" * 100)
        for trade in display:
            pnl_col = f"{float(trade.pnl):+,.0f}"
            ret_col = fmt_pct(trade.net_return_pct, signed=True)
            typer.echo(
                f"  {trade.trade_date.isoformat():<12} {trade.ticker:<6} {trade.decision:<6} "
                f"{float(trade.entry_price):>7,.0f} {float(trade.stop_price):>7,.0f} "
                f"{float(trade.target_price):>7,.0f} {float(trade.exit_price):>7,.0f} "
                f"{trade.exit_reason:<18} {ret_col:>7} {pnl_col:>10}"
            )
        typer.echo("")

    for warning in response.warnings:
        prefix = "  ⚠ " if "WARNING" in warning else "  ! "
        typer.echo(typer.style(prefix + warning, fg=typer.colors.YELLOW))
    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * width, fg=typer.colors.CYAN))
