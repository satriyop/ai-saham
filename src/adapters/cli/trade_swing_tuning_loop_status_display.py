"""Display helpers for the swing tuning loop status overview.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.trade_swing_tuning_display_formatters import format_delta, format_int
from src.application.services.swing_tuning_loop_status import (
    SwingTuningLoopStatusReport,
)


def display_swing_tuning_loop_status(
    report: SwingTuningLoopStatusReport,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Status", report.status)
    info.add_row("Next", report.next_action)
    info.add_row("Notes", " | ".join(report.notes))

    console().print("")
    console().print(panel(info, title="SWING TUNING LOOP STATUS"))

    table = compact_table()
    table.add_column("Step", style="bold cyan")
    table.add_column("State")
    table.add_column("Detail")
    latest_review = report.review.latest_review
    table.add_row(
        "Review",
        "ready" if latest_review else "missing",
        _loop_review_detail(report),
    )
    table.add_row(
        "Patch",
        _patch_state(report),
        report.patch.patch_path,
    )
    latest_apply = report.apply.latest_apply
    table.add_row(
        "Apply",
        "ready" if latest_apply else "missing",
        latest_apply.applied_at if latest_apply else report.apply.apply_log_path,
    )
    table.add_row(
        "Verify",
        _verify_state(report),
        _verify_detail(report),
    )
    measurement = report.apply.post_apply_measurement
    table.add_row(
        "Measure",
        measurement.status,
        _measurement_detail(report),
    )

    console().print("")
    console().print(panel(table, title="LOOP ARTIFACTS"))


def _patch_state(report: SwingTuningLoopStatusReport) -> str:
    if not report.patch.exists:
        return "missing"
    if report.patch.validation is None or not report.patch.validation.valid:
        return "invalid"
    if report.patch.dry_run_ready is not True:
        return "not ready"
    return "ready"


def _loop_review_detail(report: SwingTuningLoopStatusReport) -> str:
    latest_review = report.review.latest_review
    if latest_review is None:
        return "Run tune-swing --save"
    if (
        report.next_action == "RUN_TUNE_SWING_WITH_LARGER_SAMPLE"
        or latest_review.sample_status == "INSUFFICIENT_SAMPLE"
    ):
        trade_count = _sample_count(
            latest_review.trade_count,
            latest_review.min_sample_size,
        )
        candidate_count = _sample_count(
            latest_review.candidate_observation_count,
            latest_review.min_sample_size,
        )
        return (
            f"{latest_review.sample_status or 'N/A'}; "
            f"trades {trade_count}, candidates {candidate_count}"
        )
    return f"{latest_review.recorded_at} {latest_review.setup or 'N/A'}"


def _sample_count(value: int | None, minimum: int | None) -> str:
    if value is None and minimum is None:
        return "N/A"
    if minimum is None:
        return format_int(value)
    return f"{format_int(value)}/{minimum}"


def _verify_state(report: SwingTuningLoopStatusReport) -> str:
    if report.patch.verify is None:
        return "N/A"
    return "ready" if report.patch.verify.verified else "not verified"


def _verify_detail(report: SwingTuningLoopStatusReport) -> str:
    verify = report.patch.verify
    if verify is None:
        return "No patch"
    return f"{verify.verified_item_count}/{verify.item_count} verified"


def _measurement_detail(report: SwingTuningLoopStatusReport) -> str:
    measurement = report.apply.post_apply_measurement
    if measurement.status != "READY":
        return " | ".join(measurement.notes) or "N/A"
    deltas = {
        delta.name: delta.delta
        for delta in measurement.metric_deltas
    }
    return (
        f"return {format_delta(deltas.get('total_return_pct'))}, "
        f"win {format_delta(deltas.get('win_rate_pct'))}"
    )
