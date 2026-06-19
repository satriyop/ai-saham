"""
Display helpers for swing CLI commands.

Layer: Adapter
"""

from datetime import date
from decimal import Decimal

import typer

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
    typer.echo("")
    typer.echo(typer.style("=" * 102, fg=typer.colors.CYAN))
    typer.echo(typer.style("SWING BACKTEST COMPARISON", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 102, fg=typer.colors.CYAN))
    cost_bps = rows[0][1].cost_bps if rows else Decimal("0")
    typer.echo(
        f"Universe: {universe_label} | Period: {start_date} to {end_date} | "
        f"Cost: {float(cost_bps):g} bps one-way"
    )
    typer.echo("")
    typer.echo(
        f"{'VARIANT':<16} {'REGIMES':<24} {'TRADES':>7} {'RETURN':>9} "
        f"{'MAX_DD':>9} {'WIN':>8} {'PF':>8} {'SKIP_REG':>9} {'EXPOSURE':>9}"
    )
    typer.echo("-" * 102)
    for name, response in rows:
        regimes = variants_by_name[name]
        regime_label = "all" if not regimes else ",".join(regimes)
        profit_factor = (
            "INF" if response.profit_factor == float("inf")
            else "N/A" if response.profit_factor is None
            else f"{response.profit_factor:.2f}"
        )
        typer.echo(
            f"{name:<16} {regime_label:<24} {response.trade_count:>7} "
            f"{_fmt_pct(response.total_return_pct, True):>9} "
            f"{_fmt_pct(response.max_drawdown_pct, True):>9} "
            f"{_fmt_pct(response.win_rate_pct):>8} "
            f"{profit_factor:>8} "
            f"{response.skipped_by_regime:>9} "
            f"{_fmt_pct(response.exposure_pct):>9}"
        )
    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * 102, fg=typer.colors.CYAN))


def display_swing_backtest(response: SwingBacktestResponse, show_trades: int) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))
    typer.echo(typer.style("WALK-FORWARD SWING BACKTEST", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))
    typer.echo(
        f"Preset: {response.preset} | Period: {response.start_date} to {response.end_date}"
    )
    typer.echo(f"Cost: {float(response.cost_bps):g} bps one-way, applied on entry and exit")
    typer.echo(
        "Read as: the workflow scans each replay date, opens eligible signals within "
        "portfolio limits, then exits by TP/SL/max-hold."
    )
    typer.echo("")
    typer.echo(f"{'METRIC':<24} {'VALUE':>18}")
    typer.echo("-" * 46)
    typer.echo(f"{'Initial capital':<24} {float(response.initial_capital):>18,.0f}")
    typer.echo(f"{'Final equity':<24} {float(response.final_equity):>18,.0f}")
    typer.echo(f"{'Total return':<24} {_fmt_pct(response.total_return_pct, True):>18}")
    typer.echo(f"{'Max drawdown':<24} {_fmt_pct(response.max_drawdown_pct, True):>18}")
    typer.echo(f"{'Trades':<24} {response.trade_count:>18}")
    typer.echo(f"{'Win rate':<24} {_fmt_pct(response.win_rate_pct):>18}")
    typer.echo(f"{'Avg trade return':<24} {_fmt_pct(response.avg_trade_return_pct, True):>18}")
    profit_factor = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    typer.echo(f"{'Profit factor':<24} {profit_factor:>18}")
    typer.echo(f"{'Exposure days':<24} {_fmt_pct(response.exposure_pct):>18}")
    typer.echo("")
    typer.echo(
        f"Skipped: no_cash={response.skipped_no_cash}, "
        f"duplicate={response.skipped_duplicate}, "
        f"no_forward_data={response.skipped_no_forward_data}, "
        f"regime={response.skipped_by_regime}"
    )

    if response.regime_stats:
        typer.echo("")
        typer.echo("PERFORMANCE BY ENTRY REGIME")
        typer.echo("-" * 86)
        typer.echo(
            f"{'REGIME':<12} {'TRADES':>8} {'AVG_RET':>10} "
            f"{'WIN':>8} {'TOTAL_PNL':>16}"
        )
        for stat in response.regime_stats:
            typer.echo(
                f"{stat.regime:<12} {stat.count:>8} "
                f"{_fmt_pct(stat.avg_return_pct, True):>10} "
                f"{_fmt_pct(stat.win_rate_pct):>8} "
                f"{float(stat.total_pnl):>16,.0f}"
            )

    if show_trades > 0 and response.trades:
        typer.echo("")
        typer.echo("RECENT TRADES")
        typer.echo("-" * 86)
        typer.echo(
            f"{'ENTRY':<10} {'EXIT':<10} {'TICKER':<7} {'LOTS':>6} "
            f"{'RET':>9} {'PNL':>14} {'DAYS':>5} {'REASON':<10}"
        )
        for trade in response.trades[-show_trades:]:
            typer.echo(
                f"{trade.entry_date:%Y-%m-%d} {trade.exit_date:%Y-%m-%d} "
                f"{trade.ticker:<7} {trade.lots:>6} "
                f"{_fmt_pct(trade.net_return_pct, True):>9} "
                f"{float(trade.pnl):>14,.0f} {trade.holding_days:>5} "
                f"{trade.exit_reason:<10}"
            )

    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")

    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))


def display_regime(response: MarketRegimeResponse) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
    typer.echo(typer.style("MARKET REGIME", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
    typer.echo(f"Date: {response.as_of_date} | Label: {response.label} | Score: {response.score}/7")
    typer.echo("")
    typer.echo(f"{'METRIC':<30} {'VALUE':>16}")
    typer.echo("-" * 48)
    close = "N/A" if response.benchmark_close is None else f"{float(response.benchmark_close):,.2f}"
    sma20 = "N/A" if response.benchmark_sma20 is None else f"{float(response.benchmark_sma20):,.2f}"
    sma50 = "N/A" if response.benchmark_sma50 is None else f"{float(response.benchmark_sma50):,.2f}"
    typer.echo(f"{response.benchmark_ticker + ' close':<30} {close:>16}")
    typer.echo(f"{'Benchmark SMA20':<30} {sma20:>16}")
    typer.echo(f"{'Benchmark SMA50':<30} {sma50:>16}")
    typer.echo(
        f"{'Benchmark 5d return':<30} "
        f"{_fmt_pct(response.benchmark_return_5d_pct, True):>16}"
    )
    typer.echo(
        f"{'Benchmark 20d return':<30} "
        f"{_fmt_pct(response.benchmark_return_20d_pct, True):>16}"
    )
    typer.echo(f"{'Breadth above SMA20':<30} {_fmt_pct(response.breadth_above_sma20_pct):>16}")
    typer.echo(f"{'Breadth change 5d':<30} {_fmt_pct(response.breadth_change_5d_pct, True):>16}")
    typer.echo(f"{'Foreign flow breadth':<30} {_fmt_pct(response.foreign_flow_breadth_pct):>16}")
    typer.echo(f"{'Universe evaluated':<30} {response.breadth_count:>16}/{response.universe_count}")
    typer.echo(
        f"{'Flow evaluated':<30} "
        f"{response.foreign_flow_count:>16}/{response.universe_count}"
    )
    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
