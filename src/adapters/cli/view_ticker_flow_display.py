"""
Broker/bandar and insider activity panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _not_cached


def _bandar_panel(snap) -> object:
    if snap is None:
        return panel(_not_cached(), title="Broker / Bandar Signal")

    acc_color = "green" if snap.is_accumulating else ("red" if snap.is_distributing else "yellow")

    lines: list[Text] = []
    lines.append(
        Text("  Overall: ", style="dim")
        + Text(snap.broker_accdist, style=f"bold {acc_color}")
        + Text(
            f"   Score {snap.accumulation_score:+d}   Broad {snap.broad_score:+d}", style="default"
        )
    )
    lines.append(
        Text(
            f"  Today: {snap.today_accdist}   5d: {snap.five_day_accdist}   "
            f"Top1: {snap.top1_accdist} ({snap.top1_percent:.0f}%)",
            style="default",
        )
    )

    extras: list[str] = []
    if snap.top3_accdist:
        extras.append(f"Top3: {snap.top3_accdist}")
    if snap.top5_accdist:
        extras.append(f"Top5: {snap.top5_accdist}")
    if snap.top10_accdist:
        extras.append(f"Top10: {snap.top10_accdist}")
    if extras:
        lines.append(Text("  " + "   ".join(extras), style="default"))

    lines.append(Text(f"  Session: {snap.session_date}", style="dim"))

    return panel(Group(*lines), title="Broker / Bandar Signal")


def _insider_panel(txns: list) -> object:
    if not txns:
        return panel(_not_cached(), title="Insider Activity")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Name", min_width=18)
    tbl.add_column("Role", style="dim", min_width=10)
    tbl.add_column("Action", min_width=5)
    tbl.add_column("Shares", justify="right")
    tbl.add_column("Price", justify="right", style="dim")

    for t in txns[:8]:
        action_style = "green" if t.is_buy else "red"
        role_short = {"DIREKTUR": "Dir", "KOMISARIS": "Kom"}.get(
            t.role, t.role[:3] if t.role else "\u2014"
        )
        tbl.add_row(
            str(t.transaction_date),
            t.name,
            role_short,
            Text(t.action_type, style=f"bold {action_style}"),
            f"{t.shares:,}",
            f"Rp{t.price:,.0f}" if t.price > 0 else "\u2014",
        )

    return panel(tbl, title="Insider Activity (90d)")
