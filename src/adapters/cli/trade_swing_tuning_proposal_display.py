"""
Tuning proposal draft rendering for trade swing CLI display.

Renders TUNING PROPOSAL DRAFT panel by calling build_tuning_proposal_draft.
Only module allowed to call build_tuning_proposal_draft.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.swing_tuning_contracts import build_tuning_proposal_draft
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def display_swing_tuning_proposal(response: SwingBacktestResponse) -> None:
    """Display tuning proposal draft by calling build_tuning_proposal_draft.

    This is the ONLY display module allowed to call build_tuning_proposal_draft.
    Preserves candidate limit [:8] and empty candidate row exactly.
    """
    from src.adapters.cli.trade_swing_display_formatters import _quality_status_text

    draft = build_tuning_proposal_draft(response.attribution_summary)
    table = compact_table()
    table.add_column("Priority", justify="right")
    table.add_column("Strength")
    table.add_column("Dimension", style="bold cyan")
    table.add_column("Family")
    table.add_column("Evidence")
    table.add_column("Action")

    for candidate in draft.candidate_changes[:8]:
        table.add_row(
            str(candidate.priority),
            candidate.evidence_strength,
            candidate.dimension,
            candidate.config_family,
            " | ".join(candidate.evidence_buckets),
            candidate.proposed_action,
        )

    if not draft.candidate_changes:
        table.add_row(
            "0",
            "N/A",
            "N/A",
            "N/A",
            "No candidate changes",
            "blocked",
        )

    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")
    summary_table.add_row("Status", draft.status)
    summary_table.add_row("Readiness", _quality_status_text(draft.readiness_status))
    summary_table.add_row("Candidate Changes", str(len(draft.candidate_changes)))
    summary_table.add_row("Rejected Changes", str(len(draft.rejected_changes)))
    summary_table.add_row("YAML Diff", "no")
    summary_table.add_row("Human Review", "required")
    if draft.evidence_notes:
        summary_table.add_row("Notes", " | ".join(draft.evidence_notes[:3]))

    console().print("")
    console().print(
        panel(
            Group(summary_table, Text(""), table),
            title="TUNING PROPOSAL DRAFT",
            subtitle=draft.intent,
        )
    )
