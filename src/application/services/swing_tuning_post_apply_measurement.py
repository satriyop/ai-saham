"""Post-apply measurement and attribution for swing tuning review artifacts.

Layer: Application
"""

from __future__ import annotations

from typing import Any

from src.application.dto.swing_tuning_review import (
    SwingTuningAppliedPatchSummary,
    SwingTuningPostApplyMeasurement,
)
from src.application.services.swing_tuning_review_summary import (
    _dict,
    _list,
    _metric_deltas,
    _str,
    summarize_review_record,
)


def measure_post_apply(
    apply_records: list[dict],
    review_records: list[dict[str, Any]],
) -> SwingTuningPostApplyMeasurement:
    latest_apply = _latest_apply_record(apply_records)
    if latest_apply is None:
        return SwingTuningPostApplyMeasurement(
            status="NO_APPLY_LOG",
            applied_patch=None,
            baseline=None,
            candidate=None,
            metric_deltas=(),
            notes=("No swing_tuning_patch_apply records were found.",),
        )

    applied_patch = _summarize_apply_record(latest_apply)
    applied_at = applied_patch.applied_at
    if applied_at is None:
        return SwingTuningPostApplyMeasurement(
            status="APPLY_LOG_INVALID",
            applied_patch=applied_patch,
            baseline=None,
            candidate=None,
            metric_deltas=(),
            notes=("Latest apply log record has no applied_at timestamp.",),
        )

    baseline_record = _latest_review_before(review_records, applied_at)
    candidate_record = _latest_review_after(review_records, applied_at)
    baseline = summarize_review_record(baseline_record) if baseline_record else None
    candidate = summarize_review_record(candidate_record) if candidate_record else None
    if baseline is None or candidate is None:
        return SwingTuningPostApplyMeasurement(
            status="INSUFFICIENT_REVIEW_HISTORY",
            applied_patch=applied_patch,
            baseline=baseline,
            candidate=candidate,
            metric_deltas=(),
            notes=(
                "Need one saved tuning review before and one after the latest apply.",
                "Run `saham trade tune-swing --save` after applying a patch.",
            ),
        )

    return SwingTuningPostApplyMeasurement(
        status="READY",
        applied_patch=applied_patch,
        baseline=baseline,
        candidate=candidate,
        metric_deltas=_metric_deltas(baseline, candidate),
        notes=(
            "Measurement is deterministic and based on saved review artifacts.",
            "This is before/after attribution, not proof of causality.",
        ),
    )


def _latest_apply_record(records: list[dict]) -> dict[str, Any] | None:
    apply_records = [
        record
        for record in records
        if record.get("artifact_type") == "swing_tuning_patch_apply"
    ]
    if not apply_records:
        return None
    return max(
        apply_records,
        key=lambda record: str(record.get("applied_at") or ""),
    )


def _summarize_apply_record(record: dict[str, Any]) -> SwingTuningAppliedPatchSummary:
    changes = tuple(_dict(change) for change in _list(record.get("changes")))
    target_paths = tuple(
        sorted(
            target_path
            for target_path in (_str(change.get("target_path")) for change in changes)
            if target_path
        )
    )
    return SwingTuningAppliedPatchSummary(
        applied_at=_str(record.get("applied_at")),
        patch_path=_str(record.get("patch_path")),
        change_count=len(changes),
        target_paths=target_paths,
    )


def _latest_review_before(
    records: list[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any] | None:
    before = [
        record
        for record in records
        if str(record.get("recorded_at") or "") < timestamp
    ]
    return before[-1] if before else None


def _latest_review_after(
    records: list[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any] | None:
    after = [
        record
        for record in records
        if str(record.get("recorded_at") or "") > timestamp
    ]
    return after[0] if after else None
