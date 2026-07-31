"""Present-only Plan swing stage body (ADR-054 structure desk).

Board context (judgment) + multi-line structure geometry. Does not place orders
and does not re-score Action.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.tui.plan_structure_result import (
    PlanStructureResult,
    plan_structure_from_runner_object,
    structure_lines,
)


@dataclass(frozen=True)
class PlanStageView:
    text: str
    ticker: str


def present_plan_stage(
    row: Any | None,
    *,
    ticker: str,
    source: str,
    rank: int = 1,
    total: int = 1,
    result_line: str = "",
    structure: PlanStructureResult | Any | None = None,
    running: bool = False,
) -> PlanStageView:
    """Board-aware plan page: judgment context from row, structure from runner."""
    lines: list[str] = [
        f"[bold #e8e8e8]Plan · {ticker} · structure[/]",
        f"[dim]from {source}  ·  #{rank}/{total}[/]",
        "",
    ]

    if row is not None and _is_accum_row(row):
        lines.extend(_accum_facts(row))
    elif row is not None and _is_preopen_row(row):
        lines.extend(_preopen_facts(row))
    else:
        lines.append("[dim]No board row facts[/]")
        lines.append(f"  ticker {ticker}")

    lines.append("")
    lines.append("[#9b8fb8]On this page[/]")
    lines.append("  Structure desk (ADR-054): horizon / SL / TP / lots.")
    lines.append("  Action inherits screen judgment · [bold]no broker order.[/]")
    lines.append("  Paper notebook: [bold]l[/] after structure · confirm · no order.")
    lines.append("  Deep judgment: Enter judge · optional j re-judge.")
    lines.append("")

    struct = plan_structure_from_runner_object(structure) if structure is not None else None
    if struct is None and result_line:
        # Backward-compatible: summary-only runner
        struct = PlanStructureResult(summary=result_line, ticker=ticker)
    lines.extend(structure_lines(struct, running=running))

    lines.append("")
    lines.append("[dim]esc board · p re-run · l paper log · no broker order · structure only[/]")
    return PlanStageView(text="\n".join(lines), ticker=ticker)


def _accum_facts(row: Any) -> list[str]:
    from src.adapters.tui.presenters.accum_presenter import build_accum_focus

    signal = str(getattr(row, "signal", "—") or "—")
    accum = str(getattr(row, "accum", "—") or "—")
    action = str(getattr(row, "action", "—") or "—")
    gate = str(getattr(row, "gate", "—") or "—")
    why = build_accum_focus(row).why or "—"
    return [
        "[#9b8fb8]Board judgment (accum)[/]",
        f"  Action {action} · Gate {gate}  [dim](inherited by structure)[/]",
        f"  Signal {signal} · Accum {accum}",
        f"  [#d4b06a]Why[/]  {why}",
    ]


def _preopen_facts(row: Any) -> list[str]:
    from src.adapters.tui.presenters.preopen_presenter import format_preopen_why

    grade = str(getattr(row, "grade", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    why = format_preopen_why(row) or "—"
    return [
        "[#9b8fb8]Board context (pre-open)[/]",
        f"  grade {grade} · risk {risk}",
        (
            f"  IEP {getattr(row, 'iep', '—')} · Δ% {getattr(row, 'delta_pct', '—')} · "
            f"IEV {getattr(row, 'iev', '—')} · NCP {getattr(row, 'ncp', '—')}"
        ),
        f"  [#d4b06a]Why[/]  {why}",
    ]


def _is_accum_row(row: Any) -> bool:
    return all(hasattr(row, k) for k in ("signal", "accum", "action", "gate"))


def _is_preopen_row(row: Any) -> bool:
    return all(hasattr(row, k) for k in ("iep", "grade", "risk", "delta_pct"))
