"""
Tuning config diff rendering for trade swing CLI display.

Renders TUNING CONFIG DIFF DRAFT panel by calling build_tuning_config_diff_draft.
Only module allowed to call build_tuning_config_diff_draft.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.trade_swing_display_formatters import (
    _fmt_config_value,
    _fmt_count_map,
    _fmt_evidence_dimensions,
    _fmt_evidence_snapshot,
    _fmt_target_classification,
    _fmt_target_path,
)
from src.application.services.swing_tuning_contracts import build_tuning_config_diff_draft
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)


def display_swing_tuning_config_diff(response: SwingBacktestResponse) -> None:
    """Display tuning config diff draft by calling build_tuning_config_diff_draft.

    This is the ONLY display module allowed to call build_tuning_config_diff_draft.
    Preserves resolved/rejected item limit [:8].
    Preserves all labels: Can Apply, Human Review, Resolved Candidates,
    Rejected Candidates, Review Checklist.
    """
    draft = build_tuning_config_diff_draft(
        response.attribution_summary,
        document_loader=swing_tuning_document_loader(),
    )
    summary = draft.summary or {}
    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")
    summary_table.add_row("Status", draft.status)
    summary_table.add_row("Proposal", draft.proposal_status)
    summary_table.add_row(
        "Diff Items",
        str(summary.get("resolved_count", len(draft.diff_items))),
    )
    summary_table.add_row(
        "Proposed",
        str(summary.get("proposed_count", 0)),
    )
    summary_table.add_row(
        "Current Only",
        str(summary.get("current_only_count", 0)),
    )
    summary_table.add_row(
        "Rejected Items",
        str(summary.get("rejected_count", len(draft.rejected_items))),
    )
    if draft.diff_items:
        summary_table.add_row(
            "Item Statuses",
            ", ".join(sorted({item.status for item in draft.diff_items})),
        )
        summary_table.add_row(
            "Value Policies",
            _fmt_count_map(summary.get("value_policy_counts")),
        )
        summary_table.add_row(
            "Meanings",
            ", ".join(sorted({item.interpretation for item in draft.diff_items})),
        )
        summary_table.add_row(
            "Evidence Coverage",
            _fmt_count_map(summary.get("evidence_dimension_counts")),
        )
    if draft.rejected_items:
        summary_table.add_row(
            "Rejected Policies",
            ", ".join(
                sorted(
                    {
                        rejection.value_selection_policy
                        for rejection in draft.rejected_items
                    }
                )
            ),
        )
        summary_table.add_row(
            "Rejected Meanings",
            ", ".join(
                sorted(
                    {
                        rejection.interpretation
                        for rejection in draft.rejected_items
                    }
                )
            ),
        )
    summary_table.add_row("Can Apply", "no")
    summary_table.add_row("Human Review", "required")
    if draft.notes:
        summary_table.add_row("Notes", " | ".join(draft.notes[:3]))

    item_table = compact_table()
    item_table.add_column("Target", style="bold cyan")
    item_table.add_column("Class")
    item_table.add_column("Evidence")
    item_table.add_column("Current", justify="right")
    item_table.add_column("Proposed", justify="right")
    item_table.add_column("Policy", overflow="fold")
    item_table.add_column("Meaning")
    item_table.add_column("Trace")
    item_table.add_column("Rationale")
    for item in draft.diff_items[:8]:
        item_table.add_row(
            _fmt_target_path(item),
            _fmt_target_classification(item.target_classification),
            _fmt_evidence_dimensions(item),
            _fmt_config_value(item.current_value),
            _fmt_config_value(item.proposed_value),
            item.value_selection_policy,
            item.interpretation,
            _fmt_evidence_snapshot(item.evidence_snapshot),
            item.rationale,
        )
    if not draft.diff_items:
        item_table.add_row(
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "No resolved diff candidates",
        )

    rejection_table = compact_table()
    rejection_table.add_column("Target Path", style="bold cyan")
    rejection_table.add_column("Evidence")
    rejection_table.add_column("Policy")
    rejection_table.add_column("Meaning")
    rejection_table.add_column("Reason")
    for rejection in draft.rejected_items[:8]:
        rejection_table.add_row(
            rejection.target_path,
            rejection.evidence_dimension,
            rejection.value_selection_policy,
            rejection.interpretation,
            rejection.reason,
        )
    if not draft.rejected_items:
        rejection_table.add_row(
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "No rejected candidates",
        )

    checklist_table = compact_table(show_header=False)
    checklist_table.add_column("Step", style="bold cyan")
    checklist_table.add_column("Review")
    for index, item in enumerate(draft.review_checklist, start=1):
        checklist_table.add_row(str(index), item)

    console().print("")
    console().print(
        panel(
            Group(
                summary_table,
                Text(""),
                Text("Resolved Candidates", style="bold"),
                item_table,
                Text(""),
                Text("Rejected Candidates", style="bold"),
                rejection_table,
                Text(""),
                Text("Review Checklist", style="bold"),
                checklist_table,
            ),
            title="TUNING CONFIG DIFF DRAFT",
            subtitle=draft.intent,
        )
    )
