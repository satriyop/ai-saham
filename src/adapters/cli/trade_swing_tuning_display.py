"""Display helpers for saved swing tuning review runs.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.swing_tuning_review_journal import (
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
    table.add_column("Trades", justify="right")
    table.add_column("Candidates", justify="right")
    table.add_column("Return", justify="right")
    table.add_column("Win", justify="right")
    table.add_column("Diff")
    table.add_column("Proposed", justify="right")
    table.add_column("Rejected", justify="right")

    for record in report.records:
        table.add_row(
            record.recorded_at or "N/A",
            record.setup or "N/A",
            _period(record.start_date, record.end_date),
            record.sample_status or "N/A",
            _int(record.trade_count),
            _int(record.candidate_observation_count),
            _pct(record.total_return_pct, signed=True),
            _pct(record.win_rate_pct),
            record.tuning_diff_status or "N/A",
            _int(record.proposed_count),
            _int(record.rejected_count),
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
            _value(delta.baseline_value),
            _value(delta.candidate_value),
            _delta(delta.delta),
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


def _period(start_date: str | None, end_date: str | None) -> str:
    if start_date and end_date:
        return f"{start_date} to {end_date}"
    return "N/A"


def _int(value: int | None) -> str:
    return "N/A" if value is None else str(value)


def _pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    color = "green" if value >= 0 else "red"
    text = f"{value:+.2f}%" if signed else f"{value:.1f}%"
    return f"[{color}]{text}[/]"


def _value(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _delta(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        color = "green" if value >= 0 else "red"
        return f"[{color}]{value:+.2f}[/]"
    if isinstance(value, int):
        color = "green" if value >= 0 else "red"
        return f"[{color}]{value:+d}[/]"
    return str(value)
