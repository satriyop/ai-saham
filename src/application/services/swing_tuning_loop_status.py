"""Read-only status assembly for the swing tuning loop.

Intent:
    Summarize saved review, exported patch, apply log, verification, and
    post-apply measurement state in one deterministic report.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchDryRunPlanner,
    SwingTuningPatchValidationReport,
    SwingTuningPatchValidator,
    SwingTuningPatchVerifier,
    SwingTuningPatchVerifyReport,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningAppliedPatchSummary,
    SwingTuningPostApplyMeasurement,
    SwingTuningReviewJournal,
    SwingTuningReviewSummary,
)
from src.domain.ports.swing_tuning_review_store import SwingTuningReviewStore


@dataclass(frozen=True)
class SwingTuningPatchStatus:
    patch_path: str
    exists: bool
    validation: SwingTuningPatchValidationReport | None
    dry_run_ready: bool | None
    verify: SwingTuningPatchVerifyReport | None

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "exists": self.exists,
            "validation": self.validation.to_dict() if self.validation else None,
            "dry_run_ready": self.dry_run_ready,
            "verify": self.verify.to_dict() if self.verify else None,
        }


@dataclass(frozen=True)
class SwingTuningReviewStatus:
    journal_path: str
    total_records: int
    latest_review: SwingTuningReviewSummary | None

    def to_dict(self) -> dict:
        return {
            "journal_path": self.journal_path,
            "total_records": self.total_records,
            "latest_review": (
                self.latest_review.to_dict() if self.latest_review else None
            ),
        }


@dataclass(frozen=True)
class SwingTuningApplyStatus:
    apply_log_path: str
    latest_apply: SwingTuningAppliedPatchSummary | None
    post_apply_measurement: SwingTuningPostApplyMeasurement

    def to_dict(self) -> dict:
        return {
            "apply_log_path": self.apply_log_path,
            "latest_apply": (
                self.latest_apply.to_dict() if self.latest_apply else None
            ),
            "post_apply_measurement": self.post_apply_measurement.to_dict(),
        }


@dataclass(frozen=True)
class SwingTuningLoopStatusReport:
    status: str
    next_action: str
    review: SwingTuningReviewStatus
    patch: SwingTuningPatchStatus
    apply: SwingTuningApplyStatus
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "next_action": self.next_action,
            "review": self.review.to_dict(),
            "patch": self.patch.to_dict(),
            "apply": self.apply.to_dict(),
            "notes": list(self.notes),
        }


class SwingTuningLoopStatusService:
    def __init__(
        self,
        review_store: SwingTuningReviewStore,
        *,
        config_root: Path | str = Path("."),
    ) -> None:
        self._review_journal = SwingTuningReviewJournal(review_store)
        self._config_root = Path(config_root)

    def status(
        self,
        *,
        review_journal_path: Path,
        patch_path: Path,
        apply_log_path: Path,
        apply_records: list[dict],
    ) -> SwingTuningLoopStatusReport:
        review_report = self._review_journal.review(limit=1)
        latest_review = review_report.records[0] if review_report.records else None
        review_status = SwingTuningReviewStatus(
            journal_path=str(review_journal_path),
            total_records=review_report.total_records,
            latest_review=latest_review,
        )
        patch_status = self._patch_status(patch_path)
        measurement = self._review_journal.measure_latest_apply(apply_records)
        apply_status = SwingTuningApplyStatus(
            apply_log_path=str(apply_log_path),
            latest_apply=measurement.applied_patch,
            post_apply_measurement=measurement,
        )
        next_action = _next_action(review_status, patch_status, apply_status)
        return SwingTuningLoopStatusReport(
            status=_overall_status(next_action),
            next_action=next_action,
            review=review_status,
            patch=patch_status,
            apply=apply_status,
            notes=(
                "Status is read-only and based on local artifacts.",
                "Run commands explicitly; this view never applies config.",
            ),
        )

    def _patch_status(self, patch_path: Path) -> SwingTuningPatchStatus:
        if not patch_path.exists():
            return SwingTuningPatchStatus(
                patch_path=str(patch_path),
                exists=False,
                validation=None,
                dry_run_ready=None,
                verify=None,
            )
        validation = SwingTuningPatchValidator(
            config_root=self._config_root
        ).validate(patch_path)
        dry_run = SwingTuningPatchDryRunPlanner(
            config_root=self._config_root
        ).plan(patch_path)
        verify = SwingTuningPatchVerifier(config_root=self._config_root).verify(
            patch_path
        )
        return SwingTuningPatchStatus(
            patch_path=str(patch_path),
            exists=True,
            validation=validation,
            dry_run_ready=dry_run.ready,
            verify=verify,
        )


def _next_action(
    review: SwingTuningReviewStatus,
    patch: SwingTuningPatchStatus,
    apply: SwingTuningApplyStatus,
) -> str:
    if review.latest_review is None:
        return "RUN_TUNE_SWING_SAVE"
    if not patch.exists:
        return "EXPORT_TUNING_PATCH"
    if patch.validation is None or not patch.validation.valid:
        return "FIX_OR_REEXPORT_PATCH"
    if patch.dry_run_ready is not True:
        return "REVIEW_PATCH_DRY_RUN"
    if apply.latest_apply is None:
        return "APPLY_PATCH_WITH_YES"
    if patch.verify is None or not patch.verify.verified:
        return "VERIFY_OR_REAPPLY_PATCH"
    if apply.post_apply_measurement.status != "READY":
        return "RUN_TUNE_SWING_SAVE_AFTER_APPLY"
    return "REVIEW_POST_APPLY_MEASUREMENT"


def _overall_status(next_action: str) -> str:
    if next_action == "REVIEW_POST_APPLY_MEASUREMENT":
        return "READY"
    if next_action in {
        "FIX_OR_REEXPORT_PATCH",
        "REVIEW_PATCH_DRY_RUN",
        "VERIFY_OR_REAPPLY_PATCH",
    }:
        return "NEEDS_ATTENTION"
    return "IN_PROGRESS"
