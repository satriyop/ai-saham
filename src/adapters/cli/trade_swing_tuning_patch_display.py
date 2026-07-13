"""Display helpers for swing tuning patch validation, dry-run, apply, and verify.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.trade_swing_tuning_display_formatters import format_value
from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchApplyReport,
    SwingTuningPatchDryRunReport,
    SwingTuningPatchValidationReport,
    SwingTuningPatchVerifyReport,
)


def display_swing_tuning_patch_validation(
    report: SwingTuningPatchValidationReport,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Patch", report.patch_path)
    info.add_row("Artifact", report.artifact_type or "N/A")
    info.add_row("Valid", "yes" if report.valid else "no")
    info.add_row(
        "Items",
        f"{report.valid_item_count}/{report.item_count} valid",
    )
    if report.issues:
        info.add_row("Issues", " | ".join(report.issues))

    console().print("")
    console().print(panel(info, title="SWING TUNING PATCH VALIDATION"))

    if not report.item_results:
        return

    table = compact_table()
    table.add_column("Target Path")
    table.add_column("Valid")
    table.add_column("Current")
    table.add_column("Proposed")
    table.add_column("Issues")

    for item in report.item_results:
        table.add_row(
            item.target_path or "N/A",
            "yes" if item.valid else "no",
            format_value(item.current_value),
            format_value(item.proposed_value),
            " | ".join(item.issues) or "-",
        )

    console().print("")
    console().print(panel(table, title="PATCH ITEMS"))


def display_swing_tuning_patch_dry_run(
    report: SwingTuningPatchDryRunReport,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Patch", report.patch_path)
    info.add_row("Ready", "yes" if report.ready else "no")
    info.add_row("Changes", str(len(report.changes)))
    if report.issues:
        info.add_row("Issues", " | ".join(report.issues))

    console().print("")
    console().print(panel(info, title="SWING TUNING PATCH DRY RUN"))

    if not report.changes:
        return

    table = compact_table()
    table.add_column("Target Path")
    table.add_column("Current")
    table.add_column("Proposed")
    for change in report.changes:
        table.add_row(
            change.target_path,
            format_value(change.current_value),
            format_value(change.proposed_value),
        )

    console().print("")
    console().print(panel(table, title="YAML CHANGES THAT WOULD BE MADE"))


def display_swing_tuning_patch_apply(
    report: SwingTuningPatchApplyReport,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Patch", report.patch_path)
    info.add_row("Applied", "yes" if report.applied else "no")
    info.add_row("Changes", str(len(report.changes)))
    info.add_row("Log", report.log_path or "N/A")
    if report.applied_at:
        info.add_row("Applied At", report.applied_at)
    if report.issues:
        info.add_row("Issues", " | ".join(report.issues))

    console().print("")
    console().print(panel(info, title="SWING TUNING PATCH APPLY"))

    if not report.changes:
        return

    table = compact_table()
    table.add_column("Target Path")
    table.add_column("Old")
    table.add_column("New")
    for change in report.changes:
        table.add_row(
            change.target_path,
            format_value(change.old_value),
            format_value(change.new_value),
        )

    console().print("")
    console().print(panel(table, title="YAML CHANGES APPLIED"))


def display_swing_tuning_patch_verify(
    report: SwingTuningPatchVerifyReport,
) -> None:
    info = compact_table(show_header=False)
    info.add_column("Key", style="bold cyan")
    info.add_column("Value")
    info.add_row("Patch", report.patch_path)
    info.add_row("Verified", "yes" if report.verified else "no")
    info.add_row(
        "Items",
        f"{report.verified_item_count}/{report.item_count} verified",
    )
    if report.issues:
        info.add_row("Issues", " | ".join(report.issues))

    console().print("")
    console().print(panel(info, title="SWING TUNING PATCH VERIFY"))

    if not report.item_results:
        return

    table = compact_table()
    table.add_column("Target Path")
    table.add_column("Verified")
    table.add_column("Expected")
    table.add_column("Actual")
    table.add_column("Issues")
    for item in report.item_results:
        table.add_row(
            item.target_path or "N/A",
            "yes" if item.verified else "no",
            format_value(item.expected_value),
            format_value(item.actual_value),
            " | ".join(item.issues) or "-",
        )

    console().print("")
    console().print(panel(table, title="APPLIED VALUE CHECKS"))
