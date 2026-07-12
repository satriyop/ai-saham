"""Dry-run planner for swing tuning patch configurations.

Layer: Application
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.swing_tuning_config_paths import DocumentLoader
from src.application.services.swing_tuning_patch_reports import (
    SwingTuningPatchDryRunChange,
    SwingTuningPatchDryRunReport,
)
from src.application.services.swing_tuning_patch_validation import (
    SwingTuningPatchValidator,
)


class SwingTuningPatchDryRunPlanner:
    def __init__(self, document_loader: DocumentLoader) -> None:
        self._validator = SwingTuningPatchValidator(document_loader=document_loader)

    def plan(self, patch_path: Path) -> SwingTuningPatchDryRunReport:
        validation = self._validator.validate(patch_path)
        issues: list[str] = []
        if not validation.valid:
            issues.append("patch_validation_failed")
        if validation.item_count == 0:
            issues.append("patch_has_no_items")

        changes = tuple(
            SwingTuningPatchDryRunChange(
                target_path=item.target_path or "",
                current_value=item.current_value,
                proposed_value=item.proposed_value,
            )
            for item in validation.item_results
            if item.valid and item.target_path
        )
        ready = not issues and bool(changes)
        return SwingTuningPatchDryRunReport(
            patch_path=str(patch_path),
            ready=ready,
            validation=validation,
            changes=changes,
            issues=tuple(issues),
        )
