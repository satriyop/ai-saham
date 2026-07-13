"""Display helpers for post-apply swing tuning measurement.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.trade_swing_tuning_display_formatters import format_delta, format_value
from src.application.services.swing_tuning_review_journal import (
    SwingTuningPostApplyMeasurement,
)


def display_swing_tuning_post_apply_measurement(
    measurement: SwingTuningPostApplyMeasurement,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Status", measurement.status)
    if measurement.applied_patch is not None:
        info.add_row("Applied At", measurement.applied_patch.applied_at or "N/A")
        info.add_row("Patch", measurement.applied_patch.patch_path or "N/A")
        info.add_row("Changes", str(measurement.applied_patch.change_count))
    if measurement.notes:
        info.add_row("Notes", " | ".join(measurement.notes))

    console().print("")
    console().print(panel(info, title="POST-APPLY TUNING MEASUREMENT"))

    if measurement.status != "READY":
        return

    summary = compact_table(show_header=False)
    summary.add_column("Key", style="bold cyan")
    summary.add_column("Baseline")
    summary.add_column("Candidate")
    summary.add_row(
        "Recorded",
        measurement.baseline.recorded_at if measurement.baseline else "N/A",
        measurement.candidate.recorded_at if measurement.candidate else "N/A",
    )
    summary.add_row(
        "Sample",
        measurement.baseline.sample_status if measurement.baseline else "N/A",
        measurement.candidate.sample_status if measurement.candidate else "N/A",
    )
    console().print("")
    console().print(panel(summary, title="REVIEW WINDOW"))

    deltas = compact_table()
    deltas.add_column("Metric", style="bold cyan")
    deltas.add_column("Baseline", justify="right")
    deltas.add_column("Candidate", justify="right")
    deltas.add_column("Delta", justify="right")
    for delta in measurement.metric_deltas:
        deltas.add_row(
            delta.name,
            format_value(delta.baseline_value),
            format_value(delta.candidate_value),
            format_delta(delta.delta),
        )

    console().print("")
    console().print(panel(deltas, title="BEFORE / AFTER METRICS"))
