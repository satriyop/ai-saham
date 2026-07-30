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
        "[bold #e8b86d]NOTEBOOK · PAPER ONLY[/]",
        f"[bold #f0ebe3]Log paper · {t}[/]",
        "",
        "[#5c6575]GEOMETRY (from structure desk)[/]",
        f"  Entry   [bold #e8b86d]{entry or '—'}[/]",
        f"  Stop    [bold #e87a6e]{stop or '—'}[/]",
        f"  Target  [bold #7ecfb8]{target or '—'}[/]",
        f"  Lots    [bold #f0ebe3]{lots or '—'}[/]",
    ]
    if plan_id:
        lines.append(f"  Plan    {plan_id}")
    lines.extend(
        [
            "",
            "[#d4b06a]Paper only · no broker order.[/]",
            "Uses saved swing_trade_plan · CLI: trade accum log --from-plan",
            "[dim]Not learning corpus · not Action authority[/]",
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
            f"[bold #e87a6e]PAPER TAPE · REFUSED[/]\n"
            f"[bold #f0ebe3]{ticker}[/] · no write\n"
            f"[#8b92a0]{message or 'refused'}[/]\n"
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
            f"[bold #7ecfb8]PAPER TAPE · LOGGED[/]\n"
            f"[bold #f0ebe3]{ticker}[/] · notebook write{pid}\n"
            f"[#8b92a0]{geo_s}[/]\n"
            f"[#8b92a0]{message or 'logged'}[/]\n"
            "[dim]paper only · not learning · no broker order[/]"
        )
    return (
        f"[bold #d4b06a]PAPER TAPE · NO WRITE[/]\n"
        f"[bold #f0ebe3]{ticker}[/]\n"
        f"[#8b92a0]{message or '0 rows / duplicate'}[/]\n"
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
