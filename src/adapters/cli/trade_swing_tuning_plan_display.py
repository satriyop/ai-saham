"""
Tuning readiness plan rendering for trade swing CLI display.

Renders TUNING READINESS PLAN panel by calling build_tuning_readiness_plan.
This is the ONLY display module allowed to call build_tuning_readiness_plan.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.swing_tuning_contracts import build_tuning_readiness_plan
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def display_swing_tuning_plan(response: SwingBacktestResponse) -> None:
    """Render tuning readiness plan by calling build_tuning_readiness_plan.

    This is the ONLY display module allowed to call build_tuning_readiness_plan.
    Only renders the returned DTO - does not recompute readiness policy.
    """
    from src.adapters.cli.trade_swing_display_formatters import _quality_status_text

    tuning_plan = build_tuning_readiness_plan(response.attribution_summary)
    table = compact_table(show_header=False)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value")
    table.add_row("Status", _quality_status_text(tuning_plan.status))
    table.add_row(
        "Can Propose Changes",
        "[green]yes[/]" if tuning_plan.can_propose_changes else "[red]no[/]",
    )
    table.add_row(
        "Evidence Scopes",
        ", ".join(tuning_plan.allowed_evidence_scopes) or "N/A",
    )
    table.add_row(
        "Config Families",
        ", ".join(tuning_plan.allowed_config_families) or "N/A",
    )
    table.add_row("Target Count", str(tuning_plan.target_count))
    if tuning_plan.blocked_reasons:
        table.add_row("Blocked Reasons", " | ".join(tuning_plan.blocked_reasons))
    table.add_row("Intent", tuning_plan.intent)

    console().print("")
    console().print(
        panel(
            table,
            title="TUNING READINESS PLAN",
        )
    )
