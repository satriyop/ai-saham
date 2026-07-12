"""Summary and review checklist policies for swing tuning config diffs.

Layer: Application
"""

from __future__ import annotations

from typing import Iterable


def build_tuning_config_diff_summary(
    diff_items: tuple[object, ...],
    rejected_items: tuple[object, ...],
) -> dict[str, object]:
    value_policy_counts = _count_strings(
        item.value_selection_policy for item in diff_items
    )
    evidence_dimension_counts = _count_strings(
        dimension
        for item in diff_items
        for dimension in (
            item.evidence_dimensions or (item.evidence_dimension,)
        )
    )
    return {
        "resolved_count": len(diff_items),
        "proposed_count": sum(
            1 for item in diff_items if item.proposed_value is not None
        ),
        "current_only_count": sum(
            1 for item in diff_items if item.proposed_value is None
        ),
        "rejected_count": len(rejected_items),
        "value_policy_counts": value_policy_counts,
        "evidence_dimension_counts": evidence_dimension_counts,
    }


def build_tuning_config_diff_review_checklist(
    diff_items: tuple[object, ...],
    rejected_items: tuple[object, ...],
) -> tuple[str, ...]:
    checklist = [
        "Confirm sample size is sufficient for the target evidence.",
        "Confirm return spread is stable across the evidence buckets.",
        "Confirm proposed value direction matches the setup intent.",
    ]
    if any(item.proposed_value is not None for item in diff_items):
        checklist.append(
            "Review every proposed value before editing YAML manually."
        )
    if any(item.proposed_value is None for item in diff_items):
        checklist.append(
            "Inspect current-only rows before treating them as tunable."
        )
    if rejected_items:
        checklist.append(
            "Resolve rejected rows before expecting a complete tuning diff."
        )
    checklist.append(
        "Do not apply automatically; edit YAML manually only after review."
    )
    return tuple(checklist)


def _count_strings(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
