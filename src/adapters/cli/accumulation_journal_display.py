"""
Display helpers for accumulation journal CLI output.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer


def display_journal_review(
    report: Any,
    journal_path: Path,
    horizon: int,
    min_score: float,
) -> None:
    _W = 70

    typer.echo("")
    typer.echo("=" * _W)
    typer.echo("ACCUMULATION TRADE JOURNAL REVIEW")
    typer.echo("=" * _W)
    typer.echo(f"Journal  : {journal_path}")
    typer.echo(f"Entries  : {report.total_entries} total | {report.enriched_entries} with {horizon}d+ data")
    typer.echo(f"Horizon  : {horizon} trading days | min_score filter: {min_score}")

    if report.enriched_entries == 0:
        typer.echo("")
        typer.echo("No enriched entries yet — check back after market data covers the horizon.")
        typer.echo("=" * _W)
        return

    # Apply min_score filter to the enriched entries for display
    # (report already computed; we just filter display)
    def _pct(v: float | None) -> str:
        return f"{v:+.1f}%" if v is not None else "  N/A"

    def _wr(v: float | None) -> str:
        return f"{v:.0f}%" if v is not None else " N/A"

    # ── PERFORMANCE BY SCORE BUCKET ──
    typer.echo("")
    typer.echo(typer.style("PERFORMANCE BY SCORE BUCKET", fg=typer.colors.CYAN, bold=True))
    typer.echo(f"  {'BUCKET':<10} {'N':>4}  {'AVG_5D':>8}  {'AVG_10D':>8}  {'WIN_RATE_10D':>13}")
    typer.echo("  " + "-" * 50)
    for stat in report.score_buckets:
        if stat.n == 0 and min_score > 0:
            continue
        typer.echo(
            f"  {stat.bucket:<10} {stat.n:>4}  {_pct(stat.avg_return_5d):>8}  "
            f"{_pct(stat.avg_return_10d):>8}  {_wr(stat.win_rate_10d):>13}"
        )

    # ── PERFORMANCE BY PRESET DECISION ──
    if report.by_decision:
        typer.echo("")
        typer.echo(typer.style("PERFORMANCE BY PRESET DECISION", fg=typer.colors.CYAN, bold=True))
        typer.echo(
            f"  {'DECISION':<12} {'N':>4}  {'AVG_10D':>8}  {'WIN_RATE':>9}  "
            f"{'AVG_MAX_UP':>11}  {'AVG_MAX_DD':>11}"
        )
        typer.echo("  " + "-" * 62)
        for stat in report.by_decision:
            typer.echo(
                f"  {stat.decision:<12} {stat.n:>4}  {_pct(stat.avg_return_10d):>8}  "
                f"{_wr(stat.win_rate_10d):>9}  {_pct(stat.avg_max_upside):>11}  "
                f"{_pct(stat.avg_max_drawdown):>11}"
            )

    # ── PERFORMANCE BY PATTERN ──
    if report.by_pattern:
        typer.echo("")
        typer.echo(typer.style("PERFORMANCE BY PATTERN", fg=typer.colors.CYAN, bold=True))
        typer.echo(
            f"  {'PATTERN':<18} {'N':>4}  {'AVG_10D':>8}  {'WIN_RATE':>9}  "
            f"{'AVG_MAX_UP':>11}  {'AVG_MAX_DD':>11}"
        )
        typer.echo("  " + "-" * 70)
        for stat in report.by_pattern:
            typer.echo(
                f"  {stat.pattern:<18} {stat.n:>4}  {_pct(stat.avg_return_10d):>8}  "
                f"{_wr(stat.win_rate_10d):>9}  {_pct(stat.avg_max_upside):>11}  "
                f"{_pct(stat.avg_max_drawdown):>11}"
            )

    # ── SIGNAL DELTA ──
    if report.signal_deltas:
        typer.echo("")
        typer.echo(typer.style("SIGNAL DELTA (correlation with 10d return)", fg=typer.colors.CYAN, bold=True))
        typer.echo(
            f"  {'SIGNAL':<12}  {'GROUP A':<20}  {'N_A':>4}  {'AVG_A':>7}  "
            f"{'GROUP B':<20}  {'N_B':>4}  {'AVG_B':>7}"
        )
        typer.echo("  " + "-" * 82)
        for d in report.signal_deltas:
            typer.echo(
                f"  {d.signal:<12}  {d.group_a_label:<20}  {d.group_a_n:>4}  "
                f"{_pct(d.group_a_avg_10d):>7}  {d.group_b_label:<20}  "
                f"{d.group_b_n:>4}  {_pct(d.group_b_avg_10d):>7}"
            )

    typer.echo("")
    typer.echo("Note: 20+ entries needed for statistically meaningful results.")
    typer.echo("DISCLAIMER: Past performance does not predict future returns.")
    typer.echo("=" * _W)
