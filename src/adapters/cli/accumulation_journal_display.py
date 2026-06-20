"""
Display helpers for accumulation journal CLI output.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel


def display_journal_review(
    report: Any,
    journal_path: Path,
    horizon: int,
    min_score: float,
) -> None:
    # 1. Info Header
    info_table = compact_table(show_header=False)
    info_table.add_column("Key", style="bold cyan")
    info_table.add_column("Value")
    info_table.add_row("Journal", str(journal_path))
    info_table.add_row(
        "Entries",
        f"{report.total_entries} total | {report.enriched_entries} with {horizon}d+ data"
    )
    info_table.add_row(
        "Horizon",
        f"{horizon} trading days | min_score filter: {min_score}"
    )

    console().print("")
    console().print(
        panel(
            info_table,
            title="ACCUMULATION TRADE JOURNAL REVIEW"
        )
    )

    if report.enriched_entries == 0:
        console().print("")
        console().print(
            panel(
                Text("No enriched entries yet — check back after market data covers the horizon.", style="yellow"),
                title="Status"
            )
        )
        return

    # Colorized return helpers
    def _pct(v: float | None) -> str:
        if v is None:
            return "N/A"
        color = "green" if v >= 0 else "red"
        return f"[{color}]{v:+.1f}%[/]"

    def _wr(v: float | None) -> str:
        if v is None:
            return "N/A"
        color = "green" if v >= 50 else "red" if v < 40 else "white"
        return f"[{color}]{v:.0f}%[/]"

    # 2. Performance By Score Bucket
    bucket_table = compact_table()
    bucket_table.add_column("Bucket", style="bold cyan")
    bucket_table.add_column("N", justify="right")
    bucket_table.add_column("Avg 5D", justify="right")
    bucket_table.add_column("Avg 10D", justify="right")
    bucket_table.add_column("Win Rate 10D", justify="right")

    for stat in report.score_buckets:
        if stat.n == 0 and min_score > 0:
            continue
        bucket_table.add_row(
            stat.bucket,
            str(stat.n),
            _pct(stat.avg_return_5d),
            _pct(stat.avg_return_10d),
            _wr(stat.win_rate_10d)
        )

    console().print("")
    console().print(
        panel(
            bucket_table,
            title="PERFORMANCE BY SCORE BUCKET"
        )
    )

    # 3. Performance By Preset Decision
    if report.by_decision:
        decision_table = compact_table()
        decision_table.add_column("Decision", style="bold cyan")
        decision_table.add_column("N", justify="right")
        decision_table.add_column("Avg 10D", justify="right")
        decision_table.add_column("Win Rate", justify="right")
        decision_table.add_column("Avg Max Up", justify="right")
        decision_table.add_column("Avg Max DD", justify="right")

        for stat in report.by_decision:
            decision_table.add_row(
                stat.decision,
                str(stat.n),
                _pct(stat.avg_return_10d),
                _wr(stat.win_rate_10d),
                _pct(stat.avg_max_upside),
                _pct(stat.avg_max_drawdown)
            )

        console().print("")
        console().print(
            panel(
                decision_table,
                title="PERFORMANCE BY PRESET DECISION"
            )
        )

    # 4. Performance By Pattern
    if report.by_pattern:
        pattern_table = compact_table()
        pattern_table.add_column("Pattern", style="bold cyan")
        pattern_table.add_column("N", justify="right")
        pattern_table.add_column("Avg 10D", justify="right")
        pattern_table.add_column("Win Rate", justify="right")
        pattern_table.add_column("Avg Max Up", justify="right")
        pattern_table.add_column("Avg Max DD", justify="right")

        for stat in report.by_pattern:
            pattern_table.add_row(
                stat.pattern,
                str(stat.n),
                _pct(stat.avg_return_10d),
                _wr(stat.win_rate_10d),
                _pct(stat.avg_max_upside),
                _pct(stat.avg_max_drawdown)
            )

        console().print("")
        console().print(
            panel(
                pattern_table,
                title="PERFORMANCE BY PATTERN"
            )
        )

    # 5. Signal Delta
    if report.signal_deltas:
        delta_table = compact_table()
        delta_table.add_column("Signal", style="bold cyan")
        delta_table.add_column("Group A")
        delta_table.add_column("N A", justify="right")
        delta_table.add_column("Avg A", justify="right")
        delta_table.add_column("Group B")
        delta_table.add_column("N B", justify="right")
        delta_table.add_column("Avg B", justify="right")

        for d in report.signal_deltas:
            delta_table.add_row(
                d.signal,
                d.group_a_label,
                str(d.group_a_n),
                _pct(d.group_a_avg_10d),
                d.group_b_label,
                str(d.group_b_n),
                _pct(d.group_b_avg_10d)
            )

        console().print("")
        console().print(
            panel(
                delta_table,
                title="SIGNAL DELTA (correlation with 10d return)"
            )
        )

    # 6. Warnings & Footer
    footer_elements = [
        Text("Note: 20+ entries needed for statistically meaningful results.", style="yellow"),
        Text("DISCLAIMER: Past performance does not predict future returns.", style="dim italic")
    ]
    console().print("")
    console().print(
        panel(
            Group(*footer_elements),
            title="Reference Notes"
        )
    )
    console().print("")
