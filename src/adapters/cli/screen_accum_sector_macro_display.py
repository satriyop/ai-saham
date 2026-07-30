"""
Sector macro diagnostic panel for single-ticker screen accum (ADR-053 / ADR-054).

Judgment desk only — not plan swing structure. Present-only rendering of
pre-built SectorMacroContextEvidence; no re-score.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel


def _factor_value_display(series: str, value: float | None) -> str:
    """Policy series (BI_RATE) store net step counts, not fractional returns."""
    if value is None:
        return "—"
    if str(series).upper() in {"BI_RATE"}:
        return f"{value:+.0f} net"
    return f"{value * 100:+.1f}%"


def build_sector_macro_panel(
    smc: Any,
    *,
    ticker: str | None = None,
    surface: str = "screen",
) -> Any | None:
    """Return a Rich panel for sector-macro evidence, or None if empty.

    ``surface``: ``screen`` (judgment desk) or ``view`` (browse dashboard).
    Never shows Action/Gate. Always DIAGNOSTIC.
    """
    if smc is None:
        return None

    t = (ticker or "").upper().strip()
    lines: list = []
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
            table.add_column("Value")
            table.add_column("Score")
            table.add_column("Label")
            for f in smc.factors:
                table.add_row(
                    f.name,
                    f.series,
                    _factor_value_display(f.series, f.value),
                    f"{f.score:.2f}" if f.score is not None else "—",
                    f.label,
                )
            lines.append(table)

        if surface == "view":
            judgment = f"saham screen accum {t}" if t else "saham screen accum TICKER"
            footer = (
                f"  DIAGNOSTIC — no scoring impact (ADR-053). Judgment (Action / Why): {judgment}"
            )
        else:
            footer = "  DIAGNOSTIC — no scoring impact (ADR-053). Judgment desk only (ADR-054)."
        lines.append(Text(footer, style="dim"))
        for reason in list(smc.unavailable_reasons)[:2]:
            lines.append(Text(f"  ⚠ {reason}", style="dim yellow"))

    if not lines:
        return None
    return panel(Group(*lines), title="SECTOR MACRO")
