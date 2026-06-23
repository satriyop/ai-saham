"""
Display helpers for accumulation audit CLI output.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.accumulation_audit_use_case import AccumulationAuditResponse


def display_audit_summary(response: AccumulationAuditResponse, top_groups: int) -> None:
    if not response.records:
        console().print("[yellow]No replayed signals matched the audit filters.[/]")
        return

    # Metadata summary Panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")
    meta_table.add_row("Period", f"{response.start_date} to {response.end_date}")
    meta_table.add_row("Config", f"window: {response.window_days} sessions | replay dates: {response.total_replay_dates} | tickers: {response.total_tickers}")
    meta_table.add_row("Signal Counts", f"Signals: {response.total_records} | Skipped no forward data: {response.skipped_no_forward_data}")
    meta_table.add_row("Interpretation", "Read fixed-hold rows as: if you bought every matching signal at the signal-date close, what happened after 5/10/20 trading days.")

    console().print("")
    console().print(
        panel(
            meta_table,
            title="FOREIGN ACCUMULATION HISTORICAL AUDIT",
        )
    )

    # Primary Audit Table
    stats_table = compact_table()
    stats_table.add_column("Dimension", style="bold yellow")
    stats_table.add_column("Bucket", style="cyan")
    stats_table.add_column("N", justify="right")
    stats_table.add_column("Avg 5d", justify="right")
    stats_table.add_column("Avg 10d", justify="right")
    stats_table.add_column("Win 10d", justify="right")
    stats_table.add_column("Avg 20d", justify="right")
    stats_table.add_column("Max Up", justify="right")
    stats_table.add_column("Max DD", justify="right")

    for stat in response.group_stats[:top_groups]:
        def fmt(v: float | None) -> str:
            if v is None:
                return "—"
            color = "green" if v >= 0 else "red"
            return f"[{color}]{v:+.2f}%[/]"

        def fmt_win(v: float | None) -> str:
            if v is None:
                return "—"
            color = "green" if v >= 50.0 else "yellow"
            return f"[{color}]{v:.1f}%[/]"

        stats_table.add_row(
            stat.dimension,
            stat.bucket,
            str(stat.count),
            fmt(stat.avg_return_5d_pct),
            fmt(stat.avg_return_10d_pct),
            fmt_win(stat.win_rate_10d_pct),
            fmt(stat.avg_return_20d_pct),
            fmt(stat.avg_max_upside_pct),
            fmt(stat.avg_max_drawdown_pct),
        )

    console().print(stats_table)

    # Exit Simulation Panel
    if response.exit_simulations:
        exit_table = compact_table()
        exit_table.add_column("TP%", justify="right")
        exit_table.add_column("SL%", justify="right")
        exit_table.add_column("Hold", justify="right")
        exit_table.add_column("N", justify="right")
        exit_table.add_column("Avg Ret", justify="right")
        exit_table.add_column("Win", justify="right")
        exit_table.add_column("Avg Days", justify="right")
        exit_table.add_column("Stop", justify="right")
        exit_table.add_column("Target", justify="right")
        exit_table.add_column("MaxHold", justify="right")
        exit_table.add_column("Avg DD", justify="right")

        for stat in response.exit_simulations[:top_groups]:
            def fmt_pct(v: float | None, signed: bool = False) -> str:
                if v is None:
                    return "—"
                color = "green" if v >= 0 else "red"
                val_str = f"{v:+.2f}%" if signed else f"{v:.1f}%"
                return f"[{color}]{val_str}[/]"

            avg_days = "—" if stat.avg_holding_days is None else f"{stat.avg_holding_days:.1f}"
            exit_table.add_row(
                f"{stat.take_profit_pct:.1f}",
                f"{stat.stop_loss_pct:.1f}",
                str(stat.max_hold_days),
                str(stat.count),
                fmt_pct(stat.avg_return_pct, signed=True),
                fmt_pct(stat.win_rate_pct),
                avg_days,
                fmt_pct(stat.stop_rate_pct),
                fmt_pct(stat.target_rate_pct),
                fmt_pct(stat.max_hold_rate_pct),
                fmt_pct(stat.avg_max_drawdown_pct, signed=True),
            )

        best = response.exit_simulations[0]
        avg_ret = "N/A" if best.avg_return_pct is None else f"{best.avg_return_pct:+.2f}%"
        win = "N/A" if best.win_rate_pct is None else f"{best.win_rate_pct:.1f}%"
        avg_days = "N/A" if best.avg_holding_days is None else f"{best.avg_holding_days:.1f}d"

        sim_intro = Text(
            "Rows below simulate managed exits using daily high/low: stop is checked first, "
            "then target, otherwise exit at max-hold close.\n\n"
            f"Best by AVG_RET: TP {best.take_profit_pct:g}%, SL {best.stop_loss_pct:g}%, max hold {best.max_hold_days}d -> "
            f"avg {avg_ret}, win {win}, avg hold {avg_days}.\n"
        )
        if response.total_records < 30:
            sim_intro.append(
                "\nCaution: sample is small (<30 signals). Treat this as a hypothesis to retest on more dates/universes, not a final rule.",
                style="yellow"
            )

        console().print("")
        console().print(
            panel(
                Group(sim_intro, exit_table),
                title="EXIT SIMULATION",
            )
        )

    # Column Guide & Disclaimer Panel
    guide_table = compact_table()
    guide_table.add_column("Metric / Column", style="bold cyan")
    guide_table.add_column("Description")
    guide_table.add_row("AVG5D/10D/20D", "Passive close-to-close return after that many trading days.")
    guide_table.add_row("MAXUP/MAXDD", "Average best/worst close-to-close move inside the horizon.")
    guide_table.add_row("AVG_RET", "Simulated exit return after TP/SL/max-hold rules.")
    guide_table.add_row("WIN", "Percent of simulated exits with positive return.")
    guide_table.add_row("STOP/TARGET/MAXHOLD", "How often each exit reason happened.")
    guide_table.add_row("AVG_DD", "Average intratrade drawdown using daily low before exit.")

    warnings_group = []
    if response.warnings:
        for warning in response.warnings:
            warnings_group.append(Text(f"• {warning}", style="yellow"))

    footer_group = [
        Text("Column Guide", style="bold cyan"),
        guide_table,
    ]
    if warnings_group:
        footer_group.extend([Text("\nWarnings", style="bold yellow"), *warnings_group])
    footer_group.extend([
        Text("\nDISCLAIMER: Historical audit only. Not trading advice.", style="dim italic")
    ])

    console().print("")
    console().print(
        panel(
            Group(*footer_group),
            title="Reference & Disclaimers"
        )
    )
    console().print("")
