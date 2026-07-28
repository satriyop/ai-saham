"""
Sector context detail panel for saham plan swing full output.

Layer: Adapter

This module renders facts already produced by the sector context evidence
builder. DIAGNOSTIC-only: it must not imply scoring impact and must not
compute business action.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.plan_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.rich_display import compact_table, console, panel


def _spct(v: float | None) -> str:
    return f"{v * 100:+.1f}%" if v is not None else "—"


def print_sector_context_panel(ctx: SwingOutputDisplayContext) -> None:
    sector_context_evidence = ctx.evidence.sector_context_evidence
    sc_text = []
    if ctx.options.include_market_detail and sector_context_evidence is not None:
        sc = sector_context_evidence
        if sc.peer_count == 0 and sc.sector_regime == "UNKNOWN" and sc.unavailable_reasons:
            for reason in list(sc.unavailable_reasons)[:2]:
                sc_text.append(Text(f"Sector context unavailable: {reason}", style="dim"))
        else:
            _regime_style = {
                "BULLISH": "bold green",
                "BEARISH": "bold red",
                "NEUTRAL": "yellow",
                "UNKNOWN": "dim",
            }.get(sc.sector_regime, "white")
            header = Text()
            header.append(f"Sector: {sc.sector or '—'}  ", style="bold")
            header.append("Regime: ")
            header.append(sc.sector_regime, style=_regime_style)
            header.append(f"  Peers: {sc.peer_count}")
            sc_text.append(header)

            mt = compact_table()
            mt.add_column("Sector 20d")
            mt.add_column("vs IHSG")
            mt.add_column("Breadth")
            mt.add_column("vs Sector RS")
            mt.add_row(
                _spct(sc.sector_20d_return),
                _spct(sc.sector_vs_ihsg_20d),
                f"{sc.sector_breadth:.0%}" if sc.sector_breadth is not None else "—",
                _spct(sc.ticker_vs_sector_rs),
            )
            sc_text.append(mt)

            peer_tickers = list(sc.peer_tickers)
            if peer_tickers:
                shown = ", ".join(peer_tickers[:3])
                suffix = " …" if len(peer_tickers) > 3 else ""
                sc_text.append(Text(f"  Peers ({sc.peer_count}): {shown}{suffix}", style="dim"))

            sc_text.append(
                Text(
                    f"  Coverage: {sc.coverage_score:.2f}  DIAGNOSTIC — no scoring impact",
                    style="dim",
                )
            )
            for reason in list(sc.unavailable_reasons)[:2]:
                sc_text.append(Text(f"  ⚠ {reason}", style="dim yellow"))

    if sc_text:
        console().print("")
        console().print(panel(Group(*sc_text), title="SECTOR CONTEXT"))
