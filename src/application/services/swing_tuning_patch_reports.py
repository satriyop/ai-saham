"""Report DTOs and builder helpers for swing tuning patch validation, dry-run, apply, and verify.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class SwingTuningPatchVerifyItem:
    target_path: str | None
    verified: bool
    expected_value: object | None
    actual_value: object | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "verified": self.verified,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class SwingTuningPatchVerifyReport:
    patch_path: str
    verified: bool
    artifact_type: str | None
    item_count: int
    verified_item_count: int
    issues: tuple[str, ...]
    item_results: tuple[SwingTuningPatchVerifyItem, ...]

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "verified": self.verified,
            "artifact_type": self.artifact_type,
            "item_count": self.item_count,
            "verified_item_count": self.verified_item_count,
            "issues": list(self.issues),
            "item_results": [item.to_dict() for item in self.item_results],
        }


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


def _invalid_verify_report(patch_path: str, issue: str) -> SwingTuningPatchVerifyReport:
    return SwingTuningPatchVerifyReport(
        patch_path=patch_path,
        verified=False,
        artifact_type=None,
        item_count=0,
        verified_item_count=0,
        issues=(issue,),
        item_results=(),
    )
