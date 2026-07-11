"""Guarded dry-run config-diff draft building for swing tuning.

Intent:
    Resolve current config values for proposed tuning targets and attach
    deterministic, guarded suggested values for human review. Never applies
    changes, never mutates YAML, never calls AI.

Layer: Application
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.application.services.swing_backtest_attribution import (
    SwingBacktestAttributionSummary,
)
from src.application.services.swing_tuning_config_paths import (
    expand_tuning_config_paths,
    parse_tuning_config_path,
    resolve_tuning_config_value,
)
from src.application.services.swing_tuning_contracts import (
    TUNING_CONFIG_DIFF_NO_APPLY_INTENT,
    TuningConfigDiffDraft,
    TuningConfigDiffItem,
    TuningConfigDiffRejection,
    TuningEvidenceSnapshot,
    assert_tuning_config_diff_apply_block,
)
from src.application.services.swing_tuning_diff_policy import (
    build_tuning_config_diff_review_checklist,
    build_tuning_config_diff_summary,
    suggest_tuning_value,
    tuning_diff_item_priority,
    value_selection_policy_for_rejection,
)
from src.application.services.swing_tuning_proposal_builder import (
    build_tuning_proposal_draft,
)

__all__ = (
    "build_tuning_config_diff_draft",
    "dedupe_tuning_diff_items",
)


def build_tuning_config_diff_draft(
    summary: SwingBacktestAttributionSummary,
    config_root: Path | str = Path("."),
    active_setups: frozenset[str] | None = None,
) -> TuningConfigDiffDraft:
    """Build a guarded dry-run config-diff schema without mutating config.

    active_setups: when provided, only include proposal paths for the named
    setups (e.g. frozenset({"foreign-bounce"})). Prevents evidence from one
    setup's backtest contaminating unrelated setup parameter proposals.
    """
    proposal = build_tuning_proposal_draft(summary)
    notes = _unique_strings((
        "Config diff draft is dry-run only.",
        "Current values are resolved only for concrete YAML paths.",
        "Proposed values require deterministic guarded value-selection.",
        "No YAML diff, AI proposal, apply step, or config mutation is generated.",
        *proposal.evidence_notes,
    ))

    if proposal.status == "BLOCKED":
        rejected_items_tuple = tuple(
            TuningConfigDiffRejection(
                target_path="N/A",
                evidence_dimension=rejection.dimension,
                reason=f"Proposal target rejected: {rejection.reason}",
                value_selection_policy="INSUFFICIENT_EVIDENCE",
            )
            for rejection in proposal.rejected_changes
        )
        return assert_tuning_config_diff_apply_block(
            TuningConfigDiffDraft(
                intent=TUNING_CONFIG_DIFF_NO_APPLY_INTENT,
                status="BLOCKED",
                proposal_status=proposal.status,
                can_apply=False,
                requires_human_review=True,
                diff_items=(),
                rejected_items=rejected_items_tuple,
                summary=build_tuning_config_diff_summary(
                    (),
                    rejected_items_tuple,
                ),
                review_checklist=build_tuning_config_diff_review_checklist(
                    (),
                    rejected_items_tuple,
                ),
                notes=notes,
            ),
        )

    diff_items: list[TuningConfigDiffItem] = []
    rejected_items: list[TuningConfigDiffRejection] = []
    for candidate in proposal.candidate_changes:
        for target_path in candidate.yaml_paths:
            for expanded_target_path in expand_tuning_config_paths(
                target_path,
                config_root=config_root,
                active_setups=active_setups,
            ):
                parsed_target_path = parse_tuning_config_path(expanded_target_path)
                resolution = resolve_tuning_config_value(
                    parsed_target_path,
                    config_root=config_root,
                )
                if not resolution.resolved:
                    rejected_items.append(
                        TuningConfigDiffRejection(
                            target_path=expanded_target_path,
                            parsed_target_path=parsed_target_path,
                            evidence_dimension=candidate.dimension,
                            reason=resolution.unresolved_reason
                            or "config_value_not_resolved",
                            value_selection_policy=value_selection_policy_for_rejection(
                                resolution.unresolved_reason,
                            ),
                        )
                    )
                    continue

                suggestion = suggest_tuning_value(candidate, resolution)
                diff_items.append(
                    TuningConfigDiffItem(
                        target_path=expanded_target_path,
                        parsed_target_path=parsed_target_path,
                        current_value=resolution.current_value,
                        proposed_value=suggestion.proposed_value,
                        rationale=suggestion.rationale,
                        evidence_dimension=candidate.dimension,
                        confidence=suggestion.confidence,
                        status=suggestion.status,
                        value_selection_policy=suggestion.value_selection_policy,
                        evidence_snapshot=TuningEvidenceSnapshot.from_candidate(
                            candidate
                        ),
                    )
                )

    has_proposed_values = any(
        item.proposed_value is not None for item in diff_items
    )
    deduped_diff_items = dedupe_tuning_diff_items(diff_items)
    rejected_items_tuple = tuple(rejected_items)
    return assert_tuning_config_diff_apply_block(
        TuningConfigDiffDraft(
            intent=TUNING_CONFIG_DIFF_NO_APPLY_INTENT,
            status=(
                "PROPOSED_VALUES_DRY_RUN"
                if has_proposed_values
                else "READ_ONLY_VALUES"
                if diff_items
                else "SCHEMA_ONLY"
            ),
            proposal_status=proposal.status,
            can_apply=False,
            requires_human_review=True,
            diff_items=deduped_diff_items,
            rejected_items=rejected_items_tuple,
            summary=build_tuning_config_diff_summary(
                deduped_diff_items,
                rejected_items_tuple,
            ),
            review_checklist=build_tuning_config_diff_review_checklist(
                deduped_diff_items,
                rejected_items_tuple,
            ),
            notes=notes,
        )
    )


def dedupe_tuning_diff_items(
    diff_items: list[TuningConfigDiffItem],
) -> tuple[TuningConfigDiffItem, ...]:
    grouped: dict[str, list[TuningConfigDiffItem]] = {}
    for item in diff_items:
        grouped.setdefault(item.target_path, []).append(item)

    deduped: list[TuningConfigDiffItem] = []
    for target_path in sorted(grouped):
        rows = grouped[target_path]
        selected = _select_tuning_diff_item(rows)
        evidence_dimensions = _unique_strings(
            item.evidence_dimension for item in rows
        )
        deduped.append(
            TuningConfigDiffItem(
                target_path=selected.target_path,
                parsed_target_path=selected.parsed_target_path,
                current_value=selected.current_value,
                proposed_value=selected.proposed_value,
                rationale=_merged_tuning_diff_rationale(
                    selected.rationale,
                    evidence_dimensions,
                ),
                evidence_dimension=selected.evidence_dimension,
                evidence_dimensions=evidence_dimensions,
                evidence_snapshot=selected.evidence_snapshot,
                confidence=selected.confidence,
                status=selected.status,
                value_selection_policy=selected.value_selection_policy,
            )
        )
    return tuple(deduped)


def _select_tuning_diff_item(
    rows: list[TuningConfigDiffItem],
) -> TuningConfigDiffItem:
    return max(
        enumerate(rows),
        key=lambda indexed: (
            tuning_diff_item_priority(indexed[1]),
            -indexed[0],
        ),
    )[1]


def _merged_tuning_diff_rationale(
    rationale: str,
    evidence_dimensions: tuple[str, ...],
) -> str:
    if len(evidence_dimensions) <= 1:
        return rationale
    return (
        f"{rationale} Evidence dimensions: "
        f"{', '.join(evidence_dimensions)}."
    )


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
