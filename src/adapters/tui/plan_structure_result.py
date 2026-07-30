"""Structured plan-swing result for TUI structure desk (ADR-054).

Carries geometry fields from the plan runner without re-scoring Action.
Presenter reads these; widgets do not invent prices.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanStructureResult:
    """Return shape of TUI plan runner (richer than summary-only)."""

    summary: str
    ticker: str = ""
    action: str = "—"
    entry: str = "—"
    stop: str = "—"
    target: str = "—"
    lots: str = "—"
    incomplete_reason: str = ""
    plan_id_short: str = ""
    inherits_action: bool = True
    no_order: bool = True

    def has_geometry(self) -> bool:
        vals = (self.entry, self.stop, self.target, self.lots)
        return any(v not in {"", "—", None} for v in vals)


def structure_lines(result: PlanStructureResult | None, *, running: bool = False) -> list[str]:
    """Multi-line structure block for the plan stage body."""
    lines = ["[#d4b06a]Structure result[/]"]
    if running and (result is None or not (result.summary or result.has_geometry())):
        lines.append("  Running… local plan swing (structure only)")
        return lines
    if result is None:
        lines.append("  —")
        return lines

    lines.append(f"  Action {result.action}  [dim](inherited · structure only)[/]")
    lines.append(f"  Entry   {result.entry}")
    lines.append(f"  Stop    {result.stop}")
    lines.append(f"  Target  {result.target}")
    lines.append(f"  Lots    {result.lots}")
    if result.plan_id_short:
        lines.append(f"  Plan id {result.plan_id_short}")
    if result.incomplete_reason:
        lines.append(f"  [#d4b06a]Note[/]  {result.incomplete_reason}")
    if result.no_order:
        lines.append("  [bold]No broker order.[/]")
    if result.inherits_action:
        lines.append("  Action inherits screen judgment (ADR-054 structure desk).")
    # Keep one-line summary for status/notify parity
    if result.summary:
        lines.append(f"  [dim]{result.summary}[/]")
    return lines


def plan_structure_from_runner_object(obj: Any) -> PlanStructureResult:
    """Normalize runner return (dataclass or duck-typed) for the presenter."""
    if obj is None:
        return PlanStructureResult(summary="—")
    if isinstance(obj, PlanStructureResult):
        return obj
    summary = str(getattr(obj, "summary", None) or str(obj)[:200])
    return PlanStructureResult(
        summary=summary,
        ticker=str(getattr(obj, "ticker", "") or ""),
        action=str(getattr(obj, "action", "—") or "—"),
        entry=str(getattr(obj, "entry", "—") or "—"),
        stop=str(getattr(obj, "stop", "—") or "—"),
        target=str(getattr(obj, "target", "—") or "—"),
        lots=str(getattr(obj, "lots", "—") or "—"),
        incomplete_reason=str(getattr(obj, "incomplete_reason", "") or ""),
        plan_id_short=str(getattr(obj, "plan_id_short", "") or ""),
        inherits_action=bool(getattr(obj, "inherits_action", True)),
        no_order=bool(getattr(obj, "no_order", True)),
    )
