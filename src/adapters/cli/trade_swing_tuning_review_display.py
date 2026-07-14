"""Display helpers for saved swing tuning review runs and comparisons.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.trade_swing_tuning_display_formatters import (
    format_delta,
    format_int,
    format_pct,
    format_value,
    period,
)
from src.application.dto.swing_tuning_review import (
    SwingTuningReviewComparison,
    SwingTuningReviewReport,
)


def display_swing_tuning_review_report(
    report: SwingTuningReviewReport,
    journal_path: Path,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Journal", str(journal_path))
    info.add_row("Saved Runs", str(report.total_records))
    info.add_row("Displayed", str(len(report.records)))

    console().print("")
    console().print(panel(info, title="SWING TUNING REVIEW HISTORY"))

    if not report.records:
        console().print("")
        console().print(
            panel(
                Text(
                    "No saved tuning reviews yet. Run `saham trade tune-swing --save`.",
                    style="yellow",
                ),
                title="Status",
            )
        )
        return

    table = compact_table()
    table.add_column("Recorded")
    table.add_column("Setup")
    table.add_column("Period")
    table.add_column("Sample")
    table.add_column("IS Trades", justify="right")
    table.add_column("IS Return", justify="right")
    table.add_column("IS Win", justify="right")
    table.add_column("OOS Trades", justify="right")
    table.add_column("OOS Return", justify="right")
    table.add_column("OOS Win", justify="right")
    table.add_column("Diff")
    table.add_column("Proposed", justify="right")

    for record in report.records:
        oos_trades = format_int(record.oos_trade_count) if record.walk_forward_enforced else "—"
        oos_return = (
            format_pct(record.oos_total_return_pct, signed=True)
            if record.walk_forward_enforced
            else "—"
        )
        oos_win = format_pct(record.oos_win_rate_pct) if record.walk_forward_enforced else "—"
        table.add_row(
            record.recorded_at or "N/A",
            record.setup or "N/A",
            period(record.start_date, record.end_date),
            record.sample_status or "N/A",
            format_int(record.trade_count),
            format_pct(record.total_return_pct, signed=True),
            format_pct(record.win_rate_pct),
            oos_trades,
            oos_return,
            oos_win,
            record.tuning_diff_status or "N/A",
            format_int(record.proposed_count),
        )

    console().print("")
    console().print(panel(table, title="RECENT SWING TUNING REVIEWS"))


def display_swing_tuning_review_comparison(
    comparison: SwingTuningReviewComparison,
) -> None:
    if comparison.status != "READY":
        message = " | ".join(comparison.notes) or "Comparison unavailable."
        console().print("")
        console().print(panel(Text(message, style="yellow"), title="TUNING DELTA"))
        return

    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Status", comparison.status)
    info.add_row(
        "Baseline",
        comparison.baseline.recorded_at if comparison.baseline else "N/A",
    )
    info.add_row(
        "Candidate",
        comparison.candidate.recorded_at if comparison.candidate else "N/A",
    )

    delta_table = compact_table()
    delta_table.add_column("Metric", style="bold cyan")
    delta_table.add_column("Baseline", justify="right")
    delta_table.add_column("Candidate", justify="right")
    delta_table.add_column("Delta", justify="right")

    for delta in comparison.metric_deltas:
        delta_table.add_row(
            delta.name,
            format_value(delta.baseline_value),
            format_value(delta.candidate_value),
            format_delta(delta.delta),
        )

    console().print("")
    console().print(panel(info, title="TUNING COMPARISON"))
    console().print("")
    console().print(panel(delta_table, title="METRIC DELTAS"))

    target_table = compact_table()
    target_table.add_column("Change", style="bold cyan")
    target_table.add_column("Target Path")
    for path in comparison.newly_proposed_target_paths:
        target_table.add_row("new", path)
    for path in comparison.disappeared_target_paths:
        target_table.add_row("removed", path)
    if (
        not comparison.newly_proposed_target_paths
        and not comparison.disappeared_target_paths
    ):
        target_table.add_row("none", "No proposed target path changes")

    console().print("")
    console().print(panel(target_table, title="PROPOSED TARGET PATH CHANGES"))
