"""Latest-review comparison policy for swing tuning review artifacts.

Layer: Application
"""

from __future__ import annotations

from typing import Any

from src.application.dto.swing_tuning_review import SwingTuningReviewComparison
from src.application.services.swing_tuning_review_summary import (
    _dict,
    _list,
    _metric_deltas,
    _str,
    summarize_review_record,
)


def compare_latest_review(
    sorted_records: list[dict[str, Any]],
) -> SwingTuningReviewComparison:
    if len(sorted_records) < 2:
        return SwingTuningReviewComparison(
            status="INSUFFICIENT_HISTORY",
            baseline=None,
            candidate=summarize_review_record(sorted_records[0])
            if sorted_records
            else None,
            metric_deltas=(),
            newly_proposed_target_paths=(),
            disappeared_target_paths=(),
            notes=("Need at least two saved tuning reviews to compare.",),
        )

    candidate_record = sorted_records[0]
    baseline_record = sorted_records[1]
    baseline = summarize_review_record(baseline_record)
    candidate = summarize_review_record(candidate_record)
    baseline_targets = _proposed_target_paths(baseline_record)
    candidate_targets = _proposed_target_paths(candidate_record)
    notes_list = [
        "Comparison is read-only and based on saved review artifacts.",
        "Latest saved run is candidate; previous saved run is baseline.",
    ]
    if candidate.is_ratio is None or candidate.is_ratio >= 1.0:
        notes_list.append(
            "walk_forward_not_enforced: candidate review used full data "
            "(no OOS split). Run with --is-ratio 0.70 to enforce 70/30 "
            "IS/OOS split."
        )
    return SwingTuningReviewComparison(
        status="READY",
        baseline=baseline,
        candidate=candidate,
        metric_deltas=_metric_deltas(baseline, candidate),
        newly_proposed_target_paths=tuple(
            sorted(candidate_targets - baseline_targets)
        ),
        disappeared_target_paths=tuple(
            sorted(baseline_targets - candidate_targets)
        ),
        notes=tuple(notes_list),
    )


def _proposed_target_paths(record: dict[str, Any]) -> set[str]:
    tuning_diff = _dict(record.get("tuning_config_diff"))
    paths: set[str] = set()
    for item in _list(tuning_diff.get("diff_items")):
        item_dict = _dict(item)
        if item_dict.get("proposed_value") is not None:
            target_path = _str(item_dict.get("target_path"))
            if target_path:
                paths.add(target_path)
    return paths
