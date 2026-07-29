"""Plain-text desk browse formatters shared by CLI capture paths and TUI.

Policy (ranking, empty, scope) lives in application use cases — these helpers
only format use-case results (ADR-045).

Layer: Adapter (shared pure presentation)
"""

from __future__ import annotations

from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType


def _type_label(broker_type: BrokerType) -> str:
    if broker_type == BrokerType.FOREIGN:
        return "Foreign"
    if broker_type == BrokerType.LOCAL:
        return "Local"
    return "—"


def format_desk_show_text(result) -> str:
    """Plain-text desk show (same facts as CLI display_desk_show)."""
    lines = [
        f"Broker Desk · {result.broker_code} ({result.broker_name})",
        f"type {_type_label(result.broker_type)} · as of {result.as_of}",
        (
            f"Day net {format_value(result.day_net_value)} · "
            f"lot {result.day_net_lot:,} · tickers {result.day_ticker_count}"
        ),
        str(result.scope_note),
        "",
        "Top buy stocks",
    ]
    for row in result.top_buy_stocks or ():
        lines.append(f"  {row.ticker:6}  {format_value(row.net_value):>10}  lot {row.net_lot:,}")
    if not result.top_buy_stocks:
        lines.append("  —")
    lines.append("")
    lines.append("Top sell stocks")
    for row in result.top_sell_stocks or ():
        lines.append(f"  {row.ticker:6}  {format_value(row.net_value):>10}  lot {row.net_lot:,}")
    if not result.top_sell_stocks:
        lines.append("  —")
    lines.append("")
    lines.append("CLI: saham view broker show|top-stocks|flow|history " + result.broker_code)
    return "\n".join(lines)


def format_broker_list_text(desks: list[dict]) -> str:
    """Plain-text tracked desk list for TUI / capture."""
    lines = [
        "Tracked broker desks (broker_daily_flow)",
        "same job as: saham view broker list (+ latest session pulse when cached)",
        "",
        f"{'Code':4}  {'Type':8}  {'AsOf':10}  {'DayNet':>10}  {'#':>3}  Top",
        "-" * 56,
    ]
    for row in desks:
        code = str(row.get("code", "?"))
        typ = str(row.get("type", row.get("type_label", "—")))
        as_of = str(row.get("as_of", "—"))
        day_net = str(row.get("day_net", "—"))
        tickers = str(row.get("tickers", "—"))
        top = str(row.get("top_buy", "—"))
        lines.append(f"{code:4}  {typ:8}  {as_of:10}  {day_net:>10}  {tickers:>3}  {top}")
    lines.append("-" * 56)
    lines.append("Enter a row to open desk show · esc back")
    return "\n".join(lines)


def format_desk_top_stocks_text(result) -> str:
    """Plain-text top-stocks (same facts as CLI display_desk_top_stocks)."""
    lines = [
        f"Desk Top Stocks · {result.broker_code} ({result.broker_name})",
        f"type {_type_label(result.broker_type)} · date {result.date}",
        str(result.scope_note),
        "",
        "Net buy (desk)",
    ]
    for row in result.top_buy_stocks or ():
        lines.append(f"  {row.ticker:6}  {format_value(row.net_value):>10}  lot {row.net_lot:,}")
    if not result.top_buy_stocks:
        lines.append("  —")
    lines.append("")
    lines.append("Net sell (desk)")
    for row in result.top_sell_stocks or ():
        lines.append(f"  {row.ticker:6}  {format_value(row.net_value):>10}  lot {row.net_lot:,}")
    if not result.top_sell_stocks:
        lines.append("  —")
    lines.append("")
    lines.append(f"CLI: saham view broker top-stocks {result.broker_code}")
    return "\n".join(lines)


def format_desk_flow_text(result) -> str:
    """Plain-text desk flow-by-day."""
    lines = [
        f"Desk Flow by Day · {result.broker_code} ({result.broker_name})",
        f"type {_type_label(result.broker_type)}",
        str(result.scope_note),
        "",
        f"{'Date':12}  {'Net':>10}  {'Lot':>10}  Tickers",
        "-" * 44,
    ]
    for day in result.days or ():
        lines.append(
            f"{day.date.isoformat():12}  {format_value(day.net_value):>10}  "
            f"{day.net_lot:>10,}  {day.ticker_count}"
        )
    if not result.days:
        lines.append("  —")
    lines.append("")
    lines.append(f"CLI: saham view broker flow {result.broker_code}")
    return "\n".join(lines)


def format_desk_history_text(result, *, max_rows: int = 40) -> str:
    """Plain-text desk history (row-capped)."""
    pin = f" · ticker {result.pinned_ticker}" if result.pinned_ticker else ""
    lines = [
        f"Desk History · {result.broker_code} ({result.broker_name}){pin}",
        f"type {_type_label(result.broker_type)}",
        str(result.scope_note),
        "",
        f"{'Date':12}  {'Ticker':6}  {'Net':>10}  {'Lot':>8}",
        "-" * 44,
    ]
    flows = list(result.flows or ())
    shown = flows[:max_rows]
    for flow in shown:
        lines.append(
            f"{flow.date.isoformat():12}  {flow.ticker:6}  "
            f"{format_value(flow.net_value):>10}  {flow.net_lot:>8,}"
        )
    if not flows:
        lines.append("  —")
    elif len(flows) > max_rows:
        lines.append(f"  … truncated {len(flows) - max_rows} more rows")
    lines.append("")
    lines.append(f"CLI: saham view broker history {result.broker_code}")
    return "\n".join(lines)
