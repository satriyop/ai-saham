"""Present-only Enter inspect for pre-open board rows.

Text scrapers use this module; visual paint uses PreopenInspectDesk.
Act and Risk are taken from the board row — never recomputed / re-screened.

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
    """Build structured inspect text from board row (present-only, no re-screen)."""
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
        f"[bold #e8e8e8]Pre-open · {ticker}[/]",
        f"#{model.rank}/{model.total}",
    ]
    if model.board_meta:
        lines.append(f"[dim]Board[/]  {model.board_meta}")
    lines.append("")
    lines.append(f"[#d4b06a]Hero[/]  {model.action}  ·  risk {model.risk}  ·  present-only")
    lines.append(f"  IEP  {model.iep}   {model.delta_pct}")
    lines.append("")
    lines.append("[#9b8fb8]Levels[/]")
    lines.append(f"  IEV {model.iev} · NCP {model.ncp} · ΔIEV {model.delta_iev}")
    for ln in model.data_lines:
        lines.append(f"  {ln}")
    lines.append("")
    lines.append(f"[#d4b06a]← Why:[/] {model.why}")
    lines.append("")
    lines.append("[#9b8fb8]AUCTION[/]")
    for ln in model.auction_lines:
        lines.append(f"  {ln}")
    if model.warn_lines:
        lines.append("")
        lines.append("[#d4b06a]Warn[/]")
        for ln in model.warn_lines:
            lines.append(f"  {ln}")
    if model.has_detail:
        lines.append("")
        lines.append("[#9b8fb8][d] detail[/]  available")
    lines.append("")
    lines.append("[dim]esc board · d detail · p plan · v ticker · Ctrl+P[/]")

    return PreOpenEngineInspectView(text="\n".join(lines), ticker=ticker)
