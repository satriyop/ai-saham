"""
Broker/bandar, foreign-flow, and insider activity panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _fmt_idr, _fmt_vol, _not_cached
from src.domain.entities.broker_flow import ForeignFlowPoint

# Prefer a single source so multi-day nets are not mixed across providers.
FOREIGN_FLOW_SOURCE_PREFERENCE = ("stockbit", "idx")
FOREIGN_FLOW_WINDOWS = (5, 20)
FOREIGN_FLOW_PANEL_TITLE = "Foreign Flow"


def _select_foreign_flow_points(
    points_by_source: dict[str, list[ForeignFlowPoint]],
) -> tuple[list[ForeignFlowPoint], str | None]:
    """Pick the preferred non-empty foreign-flow series for the dashboard."""
    for source in FOREIGN_FLOW_SOURCE_PREFERENCE:
        points = points_by_source.get(source) or []
        if points:
            return points, source
    for source, points in points_by_source.items():
        if points:
            return points, source
    return [], None


def _window_net(points: list[ForeignFlowPoint], days: int) -> Decimal | None:
    if not points or days <= 0:
        return None
    window = points[-days:]
    return sum((p.net_val for p in window), Decimal("0"))


def _window_buy_sell_days(points: list[ForeignFlowPoint], days: int) -> tuple[int, int]:
    if not points or days <= 0:
        return 0, 0
    window = points[-days:]
    buy_days = sum(1 for p in window if p.net_val > 0)
    sell_days = len(window) - buy_days
    return buy_days, sell_days


def _fmt_signed_lot(net_lot: int) -> str:
    prefix = "-" if net_lot < 0 else ""
    return f"{prefix}{_fmt_vol(abs(net_lot))}"


def _net_style(value: Decimal) -> str:
    if value > 0:
        return "green"
    if value < 0:
        return "red"
    return "default"


def _foreign_flow_panel(points: list[ForeignFlowPoint], *, source: str | None = None) -> object:
    """Compact latest + 5d/20d foreign net flow from cached time series."""
    title = FOREIGN_FLOW_PANEL_TITLE if not source else f"{FOREIGN_FLOW_PANEL_TITLE} ({source})"
    if not points:
        return panel(_not_cached(), title=title)

    latest = points[-1]
    lines: list[Text] = []
    latest_style = _net_style(latest.net_val)
    lines.append(
        Text("  Latest ", style="dim")
        + Text(str(latest.date), style="default")
        + Text("   Net ", style="dim")
        + Text(_fmt_idr(latest.net_val), style=f"bold {latest_style}")
        + Text(f"   {_fmt_signed_lot(latest.net_lot)} lot", style="default")
    )

    for days in FOREIGN_FLOW_WINDOWS:
        net = _window_net(points, days)
        if net is None:
            continue
        buy_days, sell_days = _window_buy_sell_days(points, days)
        style = _net_style(net)
        lines.append(
            Text(f"  {days}d net ", style="dim")
            + Text(_fmt_idr(net), style=f"bold {style}")
            + Text(f"   {buy_days} buy / {sell_days} sell days", style="default")
        )

    return panel(Group(*lines), title=title)


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


# Dashboard shows recent insider history, not only a short 90d window that
# often renders empty for large-cap names with sparse filings.
INSIDER_LOOKBACK_DAYS = 365
INSIDER_PANEL_TITLE = "Insider Activity (12m)"


def _insider_panel(txns: list) -> object:
    if not txns:
        return panel(
            Text("  none in last 12 months", style="dim"),
            title=INSIDER_PANEL_TITLE,
        )

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

    return panel(tbl, title=INSIDER_PANEL_TITLE)
