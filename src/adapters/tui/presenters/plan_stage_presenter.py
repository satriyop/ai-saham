"""Present-only Plan swing stage body (no modal).

Builds context from the board row + runner result. Does not place orders.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    running: bool = False,
) -> PlanStageView:
    """Board-aware plan page: facts from row, then local-run status/result."""
    lines: list[str] = [
        f"[bold #e8e8e8]Plan · {ticker} · swing[/]",
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
    lines.append("  Auto-runs a local re-check for this ticker (screen-accum path).")
    lines.append("  [bold]No broker order.[/] Not full CLI plan swing panels.")
    lines.append("")

    if running and not result_line:
        lines.append("[#d4b06a]Running…[/]")
        lines.append("  Reading local cache · same use cases as CLI (thin)")
    elif result_line:
        lines.append("[#d4b06a]Result[/]")
        lines.append(f"  {result_line}")
    else:
        lines.append("[#d4b06a]Result[/]")
        lines.append("  —")

    lines.append("")
    lines.append("[dim]esc back to board · Ctrl+P · p re-run[/]")
    return PlanStageView(text="\n".join(lines), ticker=ticker)


def _accum_facts(row: Any) -> list[str]:
    from src.adapters.tui.presenters.accum_presenter import build_accum_focus

    signal = str(getattr(row, "signal", "—") or "—")
    accum = str(getattr(row, "accum", "—") or "—")
    action = str(getattr(row, "action", "—") or "—")
    gate = str(getattr(row, "gate", "—") or "—")
    why = build_accum_focus(row).why or "—"
    return [
        "[#9b8fb8]Board context (accum)[/]",
        f"  Action {action} · Gate {gate}",
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
