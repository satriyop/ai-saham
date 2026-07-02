"""Validation for exported swing tuning patch review artifacts.

Intent:
    Validate review-only patch JSON before any future apply flow exists. This
    service never mutates YAML.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.application.services.swing_tuning_config_paths import (
    parse_tuning_config_path,
    resolve_tuning_config_value,
)


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
