"""
Display helpers for view ticker top-brokers.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def format_value(value: Decimal) -> str:
    """Format large numbers for display (B/M/K)."""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


def _broker_type_label(broker) -> str:
    """Foreign / Local / — (unknown)."""
    from src.domain.entities.broker_flow import BrokerType

    broker_type = getattr(broker, "broker_type", None)
    if broker_type == BrokerType.UNKNOWN:
        return "—"
    if broker_type == BrokerType.FOREIGN:
        return "Foreign"
    if broker_type == BrokerType.LOCAL:
        return "Local"
    return "Foreign" if getattr(broker, "is_foreign", False) else "Local"


def _type_label_for_broker(broker) -> str:
    from src.domain.entities.broker_flow import BrokerType

    btype = getattr(broker, "broker_type", None)
    if btype == BrokerType.FOREIGN:
        return "Foreign"
    if btype == BrokerType.LOCAL:
        return "Local"
    return "Foreign" if getattr(broker, "is_foreign", False) else "Local"


# Display NetX windows for stock→desks (must match STOCK_DESK_NET_WINDOWS).
STOCK_DESK_DISPLAY_NET_WINDOWS: tuple[int, ...] = (3, 5, 7, 10, 20)


def _format_netx(value) -> str:
    return format_value(value) if value is not None else "—"


def _pulse_fields(pulse, *, net_windows: tuple[int, ...] = STOCK_DESK_DISPLAY_NET_WINDOWS) -> dict:
    """Map DeskSessionPulse → DayNet companion fields (NetX / Stk / Δ1)."""
    empty_nets = {f"net{w}": "—" for w in net_windows}
    if pulse is None:
        return {
            **empty_nets,
            "streak": "—",
            "delta1": "—",
            "sessions_in_net5": 0,
        }
    delta1_s = "—"
    if pulse.delta1 is not None:
        sign = "+" if pulse.delta1 > 0 else ""
        delta1_s = f"{sign}{format_value(pulse.delta1)}"
    nets = {}
    for w in net_windows:
        nets[f"net{w}"] = _format_netx(pulse.net_for(w))
    return {
        **nets,
        "streak": str(pulse.buy_streak),
        "delta1": delta1_s,
        "sessions_in_net5": int(getattr(pulse, "sessions_in_net5", 0) or 0),
    }


def format_ticker_top_brokers_rows(
    result,
    *,
    limit: int = 10,
    pulses: dict | None = None,
    net_windows: tuple[int, ...] = STOCK_DESK_DISPLAY_NET_WINDOWS,
) -> list:
    """Build desk rows for TUI ticker→desks table from ViewTickerTopBrokersResult.

    Ranking stays single-session tops (buyers then sellers). Optional ``pulses``
    map broker_code → DeskSessionPulse for stock-scoped multi-session NetX /
    streak / Δ1 from ``broker_daily_flow``. No broker name column (codes only).
    """
    from types import SimpleNamespace

    pulse_map = {str(k).upper(): v for k, v in (pulses or {}).items()}
    rows: list = []
    buyers = list(result.top_buyers or ())[:limit]
    sellers = list(result.top_sellers or ())[:limit]

    def _row(broker, role: str):
        code = str(broker.broker_code).upper()
        pulse = pulse_map.get(code)
        pf = _pulse_fields(pulse, net_windows=net_windows)
        # Prefer stock×desk session pulse when present (honest multi-day as_of).
        if pulse is not None:
            day_net = format_value(pulse.day_net)
            as_of = pulse.as_of.isoformat()
        else:
            day_net = format_value(broker.net_value)
            as_of = result.date.isoformat()
        row_kw = {
            "code": code,
            "type_label": _type_label_for_broker(broker),
            "role": role,
            "day_net": day_net,
            "streak": pf["streak"],
            "delta1": pf["delta1"],
            "sessions_in_net5": pf["sessions_in_net5"],
            "as_of": as_of,
            "has_pulse": pulse is not None,
        }
        for w in net_windows:
            row_kw[f"net{w}"] = pf[f"net{w}"]
        return SimpleNamespace(**row_kw)

    for b in buyers:
        rows.append(_row(b, "buy"))
    for s in sellers:
        rows.append(_row(s, "sell"))
    return rows


def display_ticker_top_brokers(
    ticker: str,
    summary,
    *,
    top_buyers=None,
    top_sellers=None,
    tops_scope_note: str | None = None,
    display_limit: int = 5,
) -> None:
    """Render top broker desks for a stock."""
    console_obj = Console()
    console_obj.print("")

    buyers = list(top_buyers if top_buyers is not None else summary.top_buyers)
    sellers = list(top_sellers if top_sellers is not None else summary.top_sellers)

    flow = summary.foreign_net_value
    flow_color = "green" if flow > 0 else "red"

    summary_text = Text()
    summary_text.append("Foreign Net Flow: ", style="bold")
    summary_text.append(
        f"{format_value(flow)} ({summary.foreign_flow_ratio:.1f}%)",
        style=f"bold {flow_color}",
    )
    summary_text.append(" | ")
    summary_text.append("Total Value: ", style="bold")
    summary_text.append(format_value(summary.total_value))
    if tops_scope_note:
        summary_text.append("\n")
        summary_text.append(tops_scope_note, style="yellow")

    panel_obj = Panel(
        summary_text,
        title=f"[bold]Top Brokers for {ticker.upper()}[/bold]",
        subtitle=f"as of {summary.date}",
        border_style="cyan",
        expand=False,
    )
    console_obj.print(panel_obj)

    buyer_title = "Top Buyers"
    seller_title = "Top Sellers"
    if tops_scope_note:
        buyer_title = "Top Buyers (tracked brokers)"
        seller_title = "Top Sellers (tracked brokers)"

    console_obj.print(f"\n[bold green]{buyer_title}[/bold green]")
    buyers_table = Table(show_header=True, header_style="bold magenta")
    buyers_table.add_column("Code", style="cyan")
    buyers_table.add_column("Name", style="white")
    buyers_table.add_column("Type", justify="center")
    buyers_table.add_column("Net Value", justify="right", style="green")
    buyers_table.add_column("Net Lot", justify="right")

    for buyer in buyers[:display_limit]:
        buyers_table.add_row(
            buyer.broker_code,
            buyer.broker_name[:20],
            _broker_type_label(buyer),
            format_value(buyer.net_value),
            f"{buyer.net_lot:,}",
        )
    console_obj.print(buyers_table)

    console_obj.print(f"\n[bold red]{seller_title}[/bold red]")
    sellers_table = Table(show_header=True, header_style="bold magenta")
    sellers_table.add_column("Code", style="cyan")
    sellers_table.add_column("Name", style="white")
    sellers_table.add_column("Type", justify="center")
    sellers_table.add_column("Net Value", justify="right", style="red")
    sellers_table.add_column("Net Lot", justify="right")

    for seller in sellers[:display_limit]:
        sellers_table.add_row(
            seller.broker_code,
            seller.broker_name[:20],
            _broker_type_label(seller),
            format_value(seller.net_value),
            f"{seller.net_lot:,}",
        )
    console_obj.print(sellers_table)
