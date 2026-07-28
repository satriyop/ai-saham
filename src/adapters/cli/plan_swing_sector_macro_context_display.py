"""
Sector macro context detail panel for plan swing full output (ADR-053).

Layer: Adapter

Renders facts already produced by SectorMacroContextEvidenceBuilder.
DIAGNOSTIC-only: must not imply scoring impact and must not compute action.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.plan_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.rich_display import compact_table, console, panel


def _pct(v: float | None) -> str:
    return f"{v * 100:+.1f}%" if v is not None else "—"


def print_sector_macro_context_panel(ctx: SwingOutputDisplayContext) -> None:
    smc = getattr(ctx.evidence, "sector_macro_context_evidence", None)
    lines: list = []
    if not (ctx.options.include_market_detail and smc is not None):
        return

    if smc.macro_regime == "UNKNOWN" and not smc.factors and smc.unavailable_reasons:
        for reason in list(smc.unavailable_reasons)[:2]:
            lines.append(Text(f"Sector macro unavailable: {reason}", style="dim"))
    else:
        style = {
            "SUPPORTIVE": "bold green",
            "HEADWIND": "bold red",
            "NEUTRAL": "yellow",
            "UNKNOWN": "dim",
        }.get(smc.macro_regime, "white")
        header = Text()
        header.append(f"Group: {smc.sector_group or '—'}  ", style="bold")
        header.append("Macro: ")
        header.append(smc.macro_regime, style=style)
        if smc.composite_score is not None:
            header.append(f"  Composite: {smc.composite_score:.2f}")
        header.append(f"  Coverage: {smc.coverage_score:.2f}")
        lines.append(header)

        if smc.factors:
            table = compact_table()
            table.add_column("Factor")
            table.add_column("Series")
            table.add_column("Return")
            table.add_column("Score")
            table.add_column("Label")
            for f in smc.factors:
                table.add_row(
                    f.name,
                    f.series,
                    _pct(f.value),
                    f"{f.score:.2f}" if f.score is not None else "—",
                    f.label,
                )
            lines.append(table)

        lines.append(
            Text(
                "  DIAGNOSTIC — no scoring impact (ADR-053)",
                style="dim",
            )
        )
        for reason in list(smc.unavailable_reasons)[:2]:
            lines.append(Text(f"  ⚠ {reason}", style="dim yellow"))

    if lines:
        console().print("")
        console().print(panel(Group(*lines), title="SECTOR MACRO"))
