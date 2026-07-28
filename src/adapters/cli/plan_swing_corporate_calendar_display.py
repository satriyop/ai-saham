"""
Corporate Calendar panel for saham plan swing.

Layer: Adapter

Renders the deterministic corporate-action event-risk context computed by
AssessCorporateActionEventRiskUseCase (src/domain/value_objects/corporate_action_event_risk.py).
Context/diagnostics only: this module must not compute severity, date
windows, or flags, and must never alter TradeSetup.action or any other
business outcome.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.plan_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.rich_display import console, panel

_SEVERITY_STYLE = {
    "blocking": "bold red",
    "warning": "yellow",
    "info": "cyan",
    "none": "dim",
}


def print_corporate_calendar_panel(ctx: SwingOutputDisplayContext) -> None:
    assessment = ctx.evidence.corporate_action_risk
    if assessment is None:
        # Repository/use case unavailable for this run — omit the panel entirely.
        return

    if not assessment.events:
        console().print("")
        console().print(Text("Corporate Calendar: no configured event risk in window", style="dim"))
        return

    lines: list[Text] = []
    for event in assessment.events:
        style = _SEVERITY_STYLE.get(event.severity.value, "")
        sign = "+" if event.days_from_as_of >= 0 else ""
        flags = ",".join(flag.value for flag in event.flags)
        line = Text()
        line.append(f"{event.severity.value.upper():<8} ", style=style)
        line.append(
            f"{event.event_type} {event.date_role} {event.event_date.isoformat()} "
            f"({sign}{event.days_from_as_of}d) {flags}"
        )
        if event.note:
            line.append(f" — {event.note}", style="dim")
        lines.append(line)

    console().print("")
    console().print(
        panel(
            Group(*lines),
            title="Corporate Calendar",
        )
    )
