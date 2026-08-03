"""Present-only Enter inspect for pre-open board rows.

Text scrapers use this module; visual paint uses PreopenInspectDesk.
Act and Risk are taken from the board row — never recomputed / re-screened.

Layer: Adapter (pure display)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.adapters.tui.presenters.preopen_presenter import PreOpenRowView
from src.adapters.tui.theme import OC


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
        f"[bold {OC.text_bright}]Pre-open · {ticker}[/]",
        f"#{model.rank}/{model.total}",
    ]
    if model.board_meta:
        lines.append(f"[dim]Board[/]  {model.board_meta}")
    lines.append("")
    lines.append(f"[{OC.brass}]Hero[/]  {model.action}  ·  risk {model.risk}  ·  present-only")
    lines.append(f"  IEP  {model.iep}   {model.delta_pct}")
    lines.append("")
    lines.append(f"[{OC.purple}]Levels[/]")
    lines.append(f"  IEV {model.iev} · NCP {model.ncp} · ΔIEV {model.delta_iev}")
    for ln in model.data_lines:
        lines.append(f"  {ln}")
    lines.append("")
    lines.append(f"[{OC.brass}]← Why:[/] {model.why}")
    lines.append("")
    lines.append(f"[{OC.purple}]AUCTION[/]")
    for ln in model.auction_lines:
        lines.append(f"  {ln}")
    if model.warn_lines:
        lines.append("")
        lines.append(f"[{OC.brass}]Warn[/]")
        for ln in model.warn_lines:
            lines.append(f"  {ln}")
    if model.has_detail:
        lines.append("")
        lines.append(f"[{OC.purple}][d] detail[/]  available")
    lines.append("")
    lines.append("[dim]esc board · d detail · p plan · v ticker · Ctrl+P[/]")

    return PreOpenEngineInspectView(text="\n".join(lines), ticker=ticker)
