"""Present-only Enter inspect for pre-open board rows.

Renders Snapshot / Levels / Auction / Data from the board row — no engine
re-run, no network, no invented Signal/Accum/setup family.

Grade and Risk are taken from the row (board-identical), never recomputed.

Layer: Adapter (pure display)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.adapters.tui.presenters.preopen_presenter import (
    PreOpenRowView,
    format_preopen_why,
)


@dataclass(frozen=True)
class PreOpenEngineInspectView:
    """Plain multi-section inspect text for the detail stage."""

    text: str
    ticker: str


def present_preopen_engine_inspect(
    row: PreOpenRowView,
    *,
    rank: int = 1,
    total: int = 1,
    snapshot_date: str = "",
    board_meta: str = "",
    warnings: tuple[str, ...] = (),
) -> PreOpenEngineInspectView:
    """Build structured inspect view from board row (present-only)."""
    ticker = str(getattr(row, "ticker", "?") or "?")
    grade = str(getattr(row, "grade", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    why = format_preopen_why(row) or "—"

    lines: list[str] = [
        f"[bold #e8e8e8]Screen · pre-open · {ticker}[/]",
        f"#{rank}/{total}",
    ]
    if board_meta:
        lines.append(f"[dim]Board[/]  {board_meta}")
    lines.append("")
    lines.append("[#d4b06a]Snapshot[/]")
    lines.append(f"  grade {grade} · risk {risk}")
    lines.append(f"  ← Why: {why}")
    lines.append("")
    lines.extend(_section_levels(row))
    lines.append("")
    lines.extend(_section_auction(row))
    lines.append("")
    lines.extend(_section_data(snapshot_date=snapshot_date, warnings=warnings))
    lines.append("")
    lines.extend(_section_notes())
    lines.append("")
    lines.append("[dim]esc back · p plan · Ctrl+P · present-only (same object as board)[/]")

    return PreOpenEngineInspectView(text="\n".join(lines), ticker=ticker)


def _section_levels(row: PreOpenRowView) -> list[str]:
    return [
        "[#9b8fb8]Levels[/]",
        (
            f"  IEP {getattr(row, 'iep', '—')} · Δ% {getattr(row, 'delta_pct', '—')} · "
            f"IEV {getattr(row, 'iev', '—')}"
        ),
        f"  NCP {getattr(row, 'ncp', '—')} · ΔIEV {getattr(row, 'delta_iev', '—')}",
    ]


def _section_auction(row: PreOpenRowView) -> list[str]:
    lines = ["[#9b8fb8]Auction / broker[/]"]
    source = getattr(row, "source", None)
    if source is None:
        lines.append("  not on this row")
        return lines
    trend = getattr(source, "trend_signal", None) or "—"
    tag = getattr(source, "opening_broker_backing_tag", None) or "—"
    score = getattr(source, "opening_broker_backing_score", None)
    streak = getattr(source, "opening_broker_buy_streak", None)
    lines.append(f"  trend {trend} · broker {tag}")
    extra: list[str] = []
    if score is not None:
        extra.append(f"backing_score {score}")
    if streak is not None:
        extra.append(f"buy_streak {streak}")
    if extra:
        lines.append(f"  {' · '.join(extra)}")
    return lines


def _section_data(*, snapshot_date: str, warnings: tuple[str, ...]) -> list[str]:
    lines = ["[#9b8fb8]Data[/]"]
    snap = snapshot_date.strip() if snapshot_date else ""
    lines.append(f"  snapshot {snap if snap else '—'}")
    lines.append("  path local IEV NCP snapshot (TUI pre-open board)")
    if warnings:
        for w in warnings[:4]:
            lines.append(f"  warning: {w}")
    return lines


def _section_notes() -> list[str]:
    return [
        "[#9b8fb8]Notes[/]",
        "  present-only · no engine re-run on Enter",
        "  full pre-open workflow risk/MCE may be absent on this snapshot path",
        "  never invents Signal / Accum / setup family",
    ]
