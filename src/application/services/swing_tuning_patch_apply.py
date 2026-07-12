"""Guarded application/mutation of swing tuning patch configurations.

Layer: Application
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.application.services.swing_tuning_config_paths import (
    DocumentLoader,
    parse_tuning_config_path,
)
from src.application.services.swing_tuning_patch_dry_run import (
    SwingTuningPatchDryRunPlanner,
)
from src.application.services.swing_tuning_patch_reports import (
    SwingTuningPatchApplyChange,
    SwingTuningPatchApplyReport,
    SwingTuningPatchDryRunReport,
)
from src.application.services.yaml_document_path import _set_document_value

TargetDirtyChecker = Callable[[Path], bool]
DocumentReader = Callable[[Path], dict]
DocumentWriter = Callable[[Path, dict], None]


class SwingTuningPatchApplier:
    def __init__(
        self,
        config_root: Path | str = Path("."),
        *,
        document_loader: DocumentLoader,
        document_reader: DocumentReader,
        document_writer: DocumentWriter,
        target_dirty_checker: TargetDirtyChecker | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config_root = Path(config_root)
        self._planner = SwingTuningPatchDryRunPlanner(document_loader=document_loader)
        self._document_reader = document_reader
        self._document_writer = document_writer
        self._target_dirty_checker = target_dirty_checker or (lambda _path: False)
        self._clock = clock or datetime.now

    def apply(
        self,
        patch_path: Path,
        *,
        confirmed: bool,
        log_path: Path | None = None,
    ) -> SwingTuningPatchApplyReport:
        dry_run = self._planner.plan(patch_path)
        issues: list[str] = []
        if not confirmed:
            issues.append("apply_confirmation_required")
        if not dry_run.ready:
            issues.append("dry_run_not_ready")

        changes = self._build_changes(dry_run)
        target_files = tuple(dict.fromkeys(change.file_path for change in changes))
        for target_file in target_files:
            full_path = self._resolve_target_file(target_file)
            if self._target_dirty_checker(full_path):
                issues.append(f"target_config_dirty:{target_file}")

        if issues:
            return SwingTuningPatchApplyReport(
                patch_path=str(patch_path),
                applied=False,
                dry_run=dry_run,
                changes=changes,
                issues=tuple(issues),
                log_path=str(log_path) if log_path else None,
                applied_at=None,
            )

        for target_file in target_files:
            file_changes = tuple(change for change in changes if change.file_path == target_file)
            self._apply_file_changes(target_file, file_changes)

        applied_at = self._clock().isoformat()
        if log_path is not None:
            self._append_log(
                log_path,
                patch_path=patch_path,
                applied_at=applied_at,
                changes=changes,
            )

        return SwingTuningPatchApplyReport(
            patch_path=str(patch_path),
            applied=True,
            dry_run=dry_run,
            changes=changes,
            issues=(),
            log_path=str(log_path) if log_path else None,
            applied_at=applied_at,
        )

    def _build_changes(
        self,
        dry_run: SwingTuningPatchDryRunReport,
    ) -> tuple[SwingTuningPatchApplyChange, ...]:
        changes: list[SwingTuningPatchApplyChange] = []
        for change in dry_run.changes:
            parsed = parse_tuning_config_path(change.target_path)
            changes.append(
                SwingTuningPatchApplyChange(
                    target_path=change.target_path,
                    file_path=parsed.file_path,
                    document_path=parsed.document_path,
                    old_value=change.current_value,
                    new_value=change.proposed_value,
                )
            )
        return tuple(changes)

    def _apply_file_changes(
        self,
        file_path: str,
        changes: tuple[SwingTuningPatchApplyChange, ...],
    ) -> None:
        full_path = self._resolve_target_file(file_path)
        document = self._document_reader(full_path)

        for change in changes:
            _set_document_value(document, change.document_path, change.new_value)

        self._document_writer(full_path, document)

    def _resolve_target_file(self, file_path: str) -> Path:
        root = self._config_root.resolve()
        full_path = (root / file_path).resolve()
        if full_path != root and root not in full_path.parents:
            raise ValueError(f"Tuning target escapes config root: {file_path}")
        return full_path

    def _append_log(
        self,
        log_path: Path,
        *,
        patch_path: Path,
        applied_at: str,
        changes: tuple[SwingTuningPatchApplyChange, ...],
    ) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "artifact_type": "swing_tuning_patch_apply",
            "applied_at": applied_at,
            "patch_path": str(patch_path),
            "changes": [change.to_dict() for change in changes],
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str))
            fh.write("\n")
