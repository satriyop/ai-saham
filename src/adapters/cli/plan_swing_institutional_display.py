"""
Institutional accumulation evidence rendering for saham plan swing.

Owns the DIAGNOSTIC-only institutional accumulation panel (foreign
institutional track, domestic bandar track, counterparty transfer) and the
flow-confirmation / bandar-distribution predicates used to annotate the
flow/broker detail panel elsewhere in the swing display.

Layer: Adapter

This module renders facts only; it does not decide TradeSetup.action or any
other scoring/business outcome.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from src.adapters.cli.rich_display import compact_table
from src.domain.value_objects.institutional_accumulation_evidence import (
    InstitutionalAccumulationEvidence,
)


def has_current_flow_confirmation(candidate: Any) -> bool:
    flow = getattr(candidate, "avg_flow_ratio", None)
    return (
        flow is not None
        and flow > 0
        and getattr(candidate, "consecutive_streak", 0) > 0
        and getattr(candidate, "net_buy_days", 0) > (getattr(candidate, "total_days", 0) / 2)
    )


def has_bandar_distribution(snapshot: Any) -> bool:
    if snapshot is None:
        return False
    if getattr(snapshot, "is_distributing", False):
        return True
    broker_accdist = str(getattr(snapshot, "broker_accdist", "") or "").lower()
    return broker_accdist in {"dis", "dist"}


def _fmt_ia(v: float | None, decimals: int = 2) -> str:
    return f"{v:.{decimals}f}" if v is not None else "—"


def _ia_panel_group(ev: InstitutionalAccumulationEvidence) -> list:
    items: list = []
    items.append(Text("DIAGNOSTIC — no scoring authority", style="dim"))

    ft = ev.foreign_institutional_track
    domestic_has_data = ev.domestic_bandar_track.coverage_score > 0.0
    foreign_has_data = ft.coverage_score > 0.0

    if not foreign_has_data and not domestic_has_data and ev.unavailable_reasons:
        for reason in list(ev.unavailable_reasons)[:3]:
            items.append(Text(f"  ⚠ {reason}", style="dim yellow"))
        return items

    items.append(Text("Foreign Institutional Track", style="bold cyan"))
    ft_table = compact_table(show_header=False)
    ft_table.add_column("Metric", style="bold")
    ft_table.add_column("Value")
    ft_table.add_row("Coverage", _fmt_ia(ft.coverage_score))
    ft_table.add_row("Conviction", _fmt_ia(ft.conviction_score))
    ft_table.add_row("Foreign participation", _fmt_ia(ft.foreign_participation_score))
    ft_table.add_row("CR4", _fmt_ia(ft.foreign_cr4_score))
    ft_table.add_row("CR8", _fmt_ia(ft.foreign_cr8_score))
    ft_table.add_row("CNFB divergence", _fmt_ia(ft.cnfb_divergence_score))
    ft_table.add_row("Foreign VWAP distance", _fmt_ia(ft.foreign_vwap_distance_score))
    items.append(ft_table)

    dt = ev.domestic_bandar_track
    items.append(Text(""))
    items.append(Text("Domestic Bandar Track", style="bold cyan"))
    dt_table = compact_table(show_header=False)
    dt_table.add_column("Metric", style="bold")
    dt_table.add_column("Value")
    dt_table.add_row("Coverage", _fmt_ia(dt.coverage_score))
    dt_table.add_row("Conviction", _fmt_ia(dt.conviction_score))
    dt_table.add_row("Broker consistency", _fmt_ia(dt.broker_consistency_score))
    dt_table.add_row("Broker reversal", _fmt_ia(dt.broker_reversal_score))
    dt_table.add_row("Accum session ratio", _fmt_ia(dt.accumulation_session_ratio))
    dt_table.add_row("Domestic buy VWAP dist", _fmt_ia(dt.domestic_buy_vwap_distance_score))
    dt_table.add_row("Broker HHI divergence", _fmt_ia(dt.broker_hhi_divergence_score))
    dt_table.add_row("Bandar broad", _fmt_ia(dt.bandar_broad_score_normalized))
    if dt.bandar_accumulation_score_normalized is not None:
        dt_table.add_row("Bandar accumulation", _fmt_ia(dt.bandar_accumulation_score_normalized))
    items.append(dt_table)

    ct = ev.counterparty_transfer
    if ct is not None:
        items.append(Text(""))
        items.append(Text("Counterparty Transfer", style="bold cyan"))
        ct_table = compact_table(show_header=False)
        ct_table.add_column("Metric", style="bold")
        ct_table.add_column("Value")
        ct_table.add_row("Transfer asymmetry", _fmt_ia(ct.transfer_asymmetry_score))
        ct_table.add_row("Buy-side HHI", _fmt_ia(ct.buy_side_hhi, 4))
        ct_table.add_row("Sell-side HHI", _fmt_ia(ct.sell_side_hhi, 4))
        items.append(ct_table)

    return items


def print_institutional_accumulation_section(
    ev: InstitutionalAccumulationEvidence,
) -> None:
    """Print the INSTITUTIONAL ACCUMULATION panel for one evidence snapshot."""
    from rich.console import Group

    from src.adapters.cli.rich_display import console, panel

    ia_items = _ia_panel_group(ev)
    console().print("")
    console().print(panel(Group(*ia_items), title="INSTITUTIONAL ACCUMULATION"))
