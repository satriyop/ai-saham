"""Validation and guarded application for exported swing tuning patch artifacts.

Intent:
    Validate review-only patch JSON, plan exact YAML changes, and apply them
    only when explicit confirmation and target-cleanliness checks pass.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from src.application.services.swing_tuning_config_paths import (
    parse_tuning_config_path,
    resolve_tuning_config_value,
)

TargetDirtyChecker = Callable[[Path], bool]


@dataclass(frozen=True)
class SwingTuningPatchItemValidation:
    target_path: str | None
    valid: bool
    current_value: object | None
    proposed_value: object | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "valid": self.valid,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class SwingTuningPatchValidationReport:
    patch_path: str
    valid: bool
    artifact_type: str | None
    item_count: int
    valid_item_count: int
    issues: tuple[str, ...]
    item_results: tuple[SwingTuningPatchItemValidation, ...]

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "valid": self.valid,
            "artifact_type": self.artifact_type,
            "item_count": self.item_count,
            "valid_item_count": self.valid_item_count,
            "issues": list(self.issues),
            "item_results": [item.to_dict() for item in self.item_results],
        }


@dataclass(frozen=True)
class SwingTuningPatchDryRunChange:
    target_path: str
    current_value: object | None
    proposed_value: object | None

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
        }


@dataclass(frozen=True)
class SwingTuningPatchDryRunReport:
    patch_path: str
    ready: bool
    validation: SwingTuningPatchValidationReport
    changes: tuple[SwingTuningPatchDryRunChange, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "ready": self.ready,
            "validation": self.validation.to_dict(),
            "changes": [change.to_dict() for change in self.changes],
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class SwingTuningPatchApplyChange:
    target_path: str
    file_path: str
    document_path: str
    old_value: object | None
    new_value: object | None

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "file_path": self.file_path,
            "document_path": self.document_path,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


@dataclass(frozen=True)
class SwingTuningPatchApplyReport:
    patch_path: str
    applied: bool
    dry_run: SwingTuningPatchDryRunReport
    changes: tuple[SwingTuningPatchApplyChange, ...]
    issues: tuple[str, ...]
    log_path: str | None
    applied_at: str | None

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "applied": self.applied,
            "dry_run": self.dry_run.to_dict(),
            "changes": [change.to_dict() for change in self.changes],
            "issues": list(self.issues),
            "log_path": self.log_path,
            "applied_at": self.applied_at,
        }


class SwingTuningPatchValidator:
    def __init__(self, config_root: Path | str = Path(".")) -> None:
        self._config_root = Path(config_root)

    def validate(self, patch_path: Path) -> SwingTuningPatchValidationReport:
        try:
            payload = json.loads(patch_path.read_text())
        except FileNotFoundError:
            return _invalid_report(str(patch_path), "patch_file_not_found")
        except json.JSONDecodeError:
            return _invalid_report(str(patch_path), "patch_json_invalid")

        issues: list[str] = []
        artifact_type = _str(payload.get("artifact_type"))
        if artifact_type != "swing_tuning_patch_review":
            issues.append("artifact_type_must_be_swing_tuning_patch_review")

        apply_block = payload.get("apply")
        if not isinstance(apply_block, dict) or apply_block.get("supported") is not False:
            issues.append("apply_supported_must_be_false")

        patch_items = payload.get("patch_items")
        if not isinstance(patch_items, list):
            issues.append("patch_items_must_be_list")
            patch_items = []

        seen_paths: set[str] = set()
        item_results = tuple(
            self._validate_item(item, seen_paths=seen_paths)
            for item in patch_items
        )
        valid = not issues and all(item.valid for item in item_results)
        return SwingTuningPatchValidationReport(
            patch_path=str(patch_path),
            valid=valid,
            artifact_type=artifact_type,
            item_count=len(patch_items),
            valid_item_count=sum(1 for item in item_results if item.valid),
            issues=tuple(issues),
            item_results=item_results,
        )

    def _validate_item(
        self,
        item: object,
        seen_paths: set[str],
    ) -> SwingTuningPatchItemValidation:
        item_issues: list[str] = []
        item_dict = item if isinstance(item, dict) else {}
        if not item_dict:
            item_issues.append("patch_item_must_be_object")

        target_path = _str(item_dict.get("target_path"))
        proposed_value = item_dict.get("proposed_value")
        current_value = item_dict.get("current_value")
        resolved_current_value: object | None = None

        if not target_path:
            item_issues.append("target_path_required")
        elif target_path in seen_paths:
            item_issues.append("duplicate_target_path")
        elif target_path is not None:
            seen_paths.add(target_path)

        if proposed_value is None:
            item_issues.append("proposed_value_required")

        if target_path:
            try:
                parsed = parse_tuning_config_path(target_path)
            except ValueError:
                item_issues.append("target_path_invalid")
            else:
                resolution = resolve_tuning_config_value(
                    parsed,
                    config_root=self._config_root,
                )
                if not resolution.resolved:
                    item_issues.append(
                        f"target_path_unresolved:{resolution.unresolved_reason}"
                    )
                else:
                    resolved_current_value = resolution.current_value
                    if current_value != resolution.current_value:
                        item_issues.append("current_value_mismatch")
                    if not _type_compatible(
                        resolution.current_value,
                        proposed_value,
                    ):
                        item_issues.append("proposed_value_type_mismatch")

        return SwingTuningPatchItemValidation(
            target_path=target_path,
            valid=not item_issues,
            current_value=resolved_current_value,
            proposed_value=proposed_value,
            issues=tuple(item_issues),
        )


class SwingTuningPatchDryRunPlanner:
    def __init__(self, config_root: Path | str = Path(".")) -> None:
        self._validator = SwingTuningPatchValidator(config_root=config_root)

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


class SwingTuningPatchApplier:
    def __init__(
        self,
        config_root: Path | str = Path("."),
        *,
        target_dirty_checker: TargetDirtyChecker | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config_root = Path(config_root)
        self._planner = SwingTuningPatchDryRunPlanner(config_root=config_root)
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
            file_changes = tuple(
                change for change in changes if change.file_path == target_file
            )
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
        with full_path.open(encoding="utf-8") as fh:
            document = yaml.safe_load(fh) or {}
        if not isinstance(document, dict):
            raise ValueError(f"YAML document must be a mapping: {file_path}")

        for change in changes:
            _set_document_value(document, change.document_path, change.new_value)

        with full_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                document,
                fh,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )

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


def _invalid_report(patch_path: str, issue: str) -> SwingTuningPatchValidationReport:
    return SwingTuningPatchValidationReport(
        patch_path=patch_path,
        valid=False,
        artifact_type=None,
        item_count=0,
        valid_item_count=0,
        issues=(issue,),
        item_results=(),
    )


def _str(value: object) -> str | None:
    return str(value) if value is not None else None


def _type_compatible(current_value: object, proposed_value: object) -> bool:
    if proposed_value is None:
        return False
    if isinstance(current_value, bool):
        return isinstance(proposed_value, bool)
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        return isinstance(proposed_value, int) and not isinstance(proposed_value, bool)
    if isinstance(current_value, float):
        return (
            isinstance(proposed_value, int | float)
            and not isinstance(proposed_value, bool)
        )
    if isinstance(current_value, str):
        return isinstance(proposed_value, str)
    return type(proposed_value) is type(current_value)


def _set_document_value(
    document: dict,
    document_path: str,
    value: object | None,
) -> None:
    current: object = document
    parts = document_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"YAML document path not found: {document_path}")
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        raise ValueError(f"YAML document path not found: {document_path}")
    current[parts[-1]] = value
