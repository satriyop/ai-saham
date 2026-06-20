"""
Display helpers for accumulation audit CLI output.

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.application.use_case.accumulation_audit import AccumulationAuditResponse


def display_audit_summary(response: AccumulationAuditResponse, top_groups: int) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 96, fg=typer.colors.CYAN))
    typer.echo(
        typer.style(
            "FOREIGN ACCUMULATION HISTORICAL AUDIT",
            fg=typer.colors.CYAN,
            bold=True,
        )
    )
    typer.echo(typer.style("=" * 96, fg=typer.colors.CYAN))
    typer.echo(
        f"Period: {response.start_date} to {response.end_date} | "
        f"window: {response.window_days} sessions | replay dates: {response.total_replay_dates} | "
        f"tickers: {response.total_tickers}"
    )
    typer.echo(
        f"Signals: {response.total_records} | "
        f"Skipped no forward data: {response.skipped_no_forward_data}"
    )
    typer.echo(
        "Read fixed-hold rows as: if you bought every matching signal at the signal-date "
        "close, what happened after 5/10/20 trading days."
    )
    typer.echo("")

    if not response.records:
        typer.echo("No replayed signals matched the audit filters.")
        return

    typer.echo(
        f"{'DIMENSION':<14} {'BUCKET':<12} {'N':>6} "
        f"{'AVG5D':>9} {'AVG10D':>9} {'WIN10D':>9} "
        f"{'AVG20D':>9} {'MAXUP':>9} {'MAXDD':>9}"
    )
    typer.echo("-" * 96)
    for stat in response.group_stats[:top_groups]:
        def fmt(v: float | None) -> str:
            return "—" if v is None else f"{v:+.2f}%"

        win = "—" if stat.win_rate_10d_pct is None else f"{stat.win_rate_10d_pct:.1f}%"
        typer.echo(
            f"{stat.dimension:<14} {stat.bucket:<12} {stat.count:>6} "
            f"{fmt(stat.avg_return_5d_pct):>9} {fmt(stat.avg_return_10d_pct):>9} "
            f"{win:>9} {fmt(stat.avg_return_20d_pct):>9} "
            f"{fmt(stat.avg_max_upside_pct):>9} {fmt(stat.avg_max_drawdown_pct):>9}"
        )

    if response.exit_simulations:
        typer.echo("")
        typer.echo("EXIT SIMULATION")
        typer.echo("-" * 96)
        best = response.exit_simulations[0]
        avg_ret = (
            "N/A" if best.avg_return_pct is None
            else f"{best.avg_return_pct:+.2f}%"
        )
        win = "N/A" if best.win_rate_pct is None else f"{best.win_rate_pct:.1f}%"
        avg_days = (
            "N/A" if best.avg_holding_days is None
            else f"{best.avg_holding_days:.1f}d"
        )
        typer.echo(
            "Rows below simulate managed exits using daily high/low: stop is checked "
            "first, then target, otherwise exit at max-hold close."
        )
        typer.echo(
            f"Best by AVG_RET: TP {best.take_profit_pct:g}%, "
            f"SL {best.stop_loss_pct:g}%, max hold {best.max_hold_days}d -> "
            f"avg {avg_ret}, win {win}, avg hold {avg_days}."
        )
        if response.total_records < 30:
            typer.echo(
                "Caution: sample is small (<30 signals). Treat this as a hypothesis "
                "to retest on more dates/universes, not a final rule."
            )
        typer.echo("")
        typer.echo(
            f"{'TP%':>6} {'SL%':>6} {'HOLD':>6} {'N':>6} "
            f"{'AVG_RET':>9} {'WIN':>8} {'AVG_DAYS':>9} "
            f"{'STOP':>8} {'TARGET':>8} {'MAXHOLD':>8} {'AVG_DD':>9}"
        )
        for stat in response.exit_simulations[:top_groups]:
            def fmt_pct(v: float | None, signed: bool = False) -> str:
                if v is None:
                    return "—"
                return f"{v:+.2f}%" if signed else f"{v:.1f}%"

            avg_days = "—" if stat.avg_holding_days is None else f"{stat.avg_holding_days:.1f}"
            typer.echo(
                f"{stat.take_profit_pct:>6.1f} {stat.stop_loss_pct:>6.1f} "
                f"{stat.max_hold_days:>6} {stat.count:>6} "
                f"{fmt_pct(stat.avg_return_pct, signed=True):>9} "
                f"{fmt_pct(stat.win_rate_pct):>8} {avg_days:>9} "
                f"{fmt_pct(stat.stop_rate_pct):>8} "
                f"{fmt_pct(stat.target_rate_pct):>8} "
                f"{fmt_pct(stat.max_hold_rate_pct):>8} "
                f"{fmt_pct(stat.avg_max_drawdown_pct, signed=True):>9}"
            )

    typer.echo("")
    typer.echo("COLUMN GUIDE")
    typer.echo("-" * 40)
    typer.echo("AVG5D/10D/20D: passive close-to-close return after that many trading days.")
    typer.echo("MAXUP/MAXDD: average best/worst close-to-close move inside the horizon.")
    typer.echo("AVG_RET: simulated exit return after TP/SL/max-hold rules.")
    typer.echo("WIN: percent of simulated exits with positive return.")
    typer.echo("STOP/TARGET/MAXHOLD: how often each exit reason happened.")
    typer.echo("AVG_DD: average intratrade drawdown using daily low before exit.")

    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")

    typer.echo("")
    typer.echo("DISCLAIMER: Historical audit only. Not trading advice.")
    typer.echo(typer.style("=" * 96, fg=typer.colors.CYAN))

