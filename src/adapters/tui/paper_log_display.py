"""Paper notebook confirm + outcome tape (design: tui-paper-journal.html).

Present-only geometry from plan structure. No Action re-score, no orders.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any


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
        "[bold #c9a68a]PAPER TAPE · CONFIRM[/]",
        f"[bold #e8e8e8]Notebook · {t}[/]",
        "",
        "[#555555]GEOMETRY · from plan structure[/]",
        f"  Entry   [bold #c9a68a]{entry or '—'}[/]",
        f"  Stop    [bold #c97a72]{stop or '—'}[/]",
        f"  Target  [bold #6fbf8a]{target or '—'}[/]",
        f"  Lots    [bold #e8e8e8]{lots or '—'}[/]",
    ]
    if plan_id:
        lines.append(f"  Plan    {plan_id}")
    lines.extend(
        [
            "",
            "[#d4b06a]Paper only · no broker order.[/]",
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
            f"[bold #c97a72]PAPER TAPE · REFUSED[/]\n"
            f"[bold #e8e8e8]{ticker}[/] · no write\n"
            f"[#7a7a7a]{message or 'refused'}[/]\n"
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
            f"[bold #6fbf8a]PAPER TAPE · LOGGED[/]\n"
            f"[bold #e8e8e8]{ticker}[/] · notebook write{pid}\n"
            f"[#7a7a7a]{geo_s}[/]\n"
            f"[#7a7a7a]{message or 'logged'}[/]\n"
            "[dim]paper only · no broker order[/]"
        )
    return (
        f"[bold #d4b06a]PAPER TAPE · NO WRITE[/]\n"
        f"[bold #e8e8e8]{ticker}[/]\n"
        f"[#7a7a7a]{message or '0 rows / duplicate'}[/]\n"
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
