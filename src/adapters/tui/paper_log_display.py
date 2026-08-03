"""Paper notebook confirm + outcome tape (design: tui-paper-journal.html).

Present-only geometry from plan structure. No Action re-score, no orders.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from src.adapters.tui.theme import OC


def format_paper_confirm_body(
    *,
    ticker: str,
    entry: str,
    stop: str,
    target: str,
    lots: str,
    plan_id: str = "",
) -> str:
    """Notebook-style confirm body for PaperLogConfirmModal."""
    t = (ticker or "—").strip().upper() or "—"
    lines = [
        f"[bold {OC.peach}]PAPER TAPE · CONFIRM[/]",
        f"[bold {OC.text_bright}]Notebook · {t}[/]",
        "",
        f"[{OC.text_mute}]GEOMETRY · from plan structure[/]",
        f"  Entry   [bold {OC.peach}]{entry or '—'}[/]",
        f"  Stop    [bold {OC.coral}]{stop or '—'}[/]",
        f"  Target  [bold {OC.mint}]{target or '—'}[/]",
        f"  Lots    [bold {OC.text_bright}]{lots or '—'}[/]",
    ]
    if plan_id:
        lines.append(f"  Plan    {plan_id}")
    lines.extend(
        [
            "",
            f"[{OC.brass}]Paper only · no broker order.[/]",
            "[dim]Notebook write · geometry from plan structure[/]",
        ]
    )
    return "\n".join(lines)


def format_paper_outcome_tape(result: Any) -> str:
    """Outcome tape after confirm — written / refused / failed."""
    ticker = str(getattr(result, "ticker", "—") or "—")
    message = str(getattr(result, "message", "") or "")
    refused = bool(getattr(result, "refused", False))
    written = bool(getattr(result, "written", False))
    entry = str(getattr(result, "planned_entry", "") or "")
    stop = str(getattr(result, "planned_stop", "") or "")
    target = str(getattr(result, "planned_target", "") or "")
    plan_id = str(getattr(result, "plan_id", "") or "")

    if refused:
        return (
            f"[bold {OC.coral}]PAPER TAPE · REFUSED[/]\n"
            f"[bold {OC.text_bright}]{ticker}[/] · no write\n"
            f"[{OC.text_dim}]{message or 'refused'}[/]\n"
            "[dim]no broker order · plan stage still open[/]"
        )
    if written:
        geo = []
        if entry:
            geo.append(f"entry {entry}")
        if stop:
            geo.append(f"stop {stop}")
        if target:
            geo.append(f"target {target}")
        geo_s = " · ".join(geo) if geo else "geometry saved"
        pid = f" · plan {plan_id}" if plan_id else ""
        return (
            f"[bold {OC.mint}]PAPER TAPE · LOGGED[/]\n"
            f"[bold {OC.text_bright}]{ticker}[/] · notebook write{pid}\n"
            f"[{OC.text_dim}]{geo_s}[/]\n"
            f"[{OC.text_dim}]{message or 'logged'}[/]\n"
            "[dim]paper only · no broker order[/]"
        )
    return (
        f"[bold {OC.brass}]PAPER TAPE · NO WRITE[/]\n"
        f"[bold {OC.text_bright}]{ticker}[/]\n"
        f"[{OC.text_dim}]{message or '0 rows / duplicate'}[/]\n"
        "[dim]no broker order[/]"
    )


def plan_text_from_structure(struct: Any, *, ticker: str) -> str:
    """Build confirm plan_text from PlanStructureResult fields only."""
    entry = str(getattr(struct, "entry", "—") or "—")
    stop = str(getattr(struct, "stop", "—") or "—")
    target = str(getattr(struct, "target", "—") or "—")
    lots = str(getattr(struct, "lots", "—") or "—")
    plan_id = str(getattr(struct, "plan_id_short", "") or "")
    return format_paper_confirm_body(
        ticker=ticker,
        entry=entry,
        stop=stop,
        target=target,
        lots=lots,
        plan_id=plan_id,
    )
