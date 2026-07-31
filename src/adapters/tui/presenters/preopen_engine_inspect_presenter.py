"""Present-only Enter inspect for pre-open board rows.

Text scrapers use this module; visual paint uses PreopenInspectDesk.
Grade and Risk are taken from the board row — never recomputed.

Layer: Adapter (pure display)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.adapters.tui.presenters.preopen_presenter import PreOpenRowView


@dataclass(frozen=True)
class PreOpenEngineInspectView:
    """Plain multi-section inspect text for scrapers / detail_text."""

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
    """Build structured inspect text from board row (present-only)."""
    from src.adapters.tui.preopen_inspect_model import build_preopen_inspect_model

    model = build_preopen_inspect_model(
        row,
        rank=rank,
        total=total,
        snapshot_date=snapshot_date,
        board_meta=board_meta,
        warnings=warnings,
    )
    ticker = model.ticker
    lines: list[str] = [
        f"[bold #e8e8e8]Screen · pre-open · {ticker}[/]",
        f"#{model.rank}/{model.total}",
    ]
    if model.board_meta:
        lines.append(f"[dim]Board[/]  {model.board_meta}")
    lines.append("")
    lines.append("[#d4b06a]Snapshot[/]")
    lines.append(f"  grade {model.grade} · risk {model.risk}")
    lines.append(f"  ← Why: {model.why}")
    lines.append("")
    lines.append("[#9b8fb8]Levels[/]")
    lines.append(f"  IEP {model.iep} · Δ% {model.delta_pct} · IEV {model.iev}")
    lines.append(f"  NCP {model.ncp} · ΔIEV {model.delta_iev}")
    lines.append("")
    lines.append("[#9b8fb8]Auction / broker[/]")
    for ln in model.auction_lines:
        lines.append(f"  {ln}")
    lines.append("")
    lines.append("[#9b8fb8]Data[/]")
    for ln in model.data_lines:
        lines.append(f"  {ln}")
    if model.warn_lines:
        lines.append("")
        lines.append("[#9b8fb8]Warn[/]")
        for ln in model.warn_lines:
            lines.append(f"  {ln}")
    lines.append("")
    lines.append("[#9b8fb8]Flags[/]  why · auction+ · warn · d detail")
    lines.append("")
    lines.append("[dim]esc back · p plan · Ctrl+P · d detail[/]")

    return PreOpenEngineInspectView(text="\n".join(lines), ticker=ticker)
