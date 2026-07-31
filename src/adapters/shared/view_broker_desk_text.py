"""Plain-text desk browse formatters shared by CLI capture paths and TUI.

Policy (ranking, empty, scope) lives in application use cases — these helpers
only format use-case results (ADR-045).

Layer: Adapter (shared pure presentation)
"""

from __future__ import annotations

from src.adapters.shared.view_number_format import format_value
from src.adapters.shared.view_ticker_top_brokers_rows import format_netx_display
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


def format_desk_calendar_text(result) -> str:
    """Plain-text desk session calendar (CLI + TUI scraper)."""
    lines = [
        f"Desk Calendar · {result.broker_code} ({result.broker_name})",
        (
            f"type {_type_label(result.broker_type)} · as of {result.as_of} · "
            f"sessions {result.sessions_cached}"
        ),
        str(result.scope_note),
        "",
        f"{'Date':12}  {'Top':6}  {'Net':>10}  {'Buy':>10}  {'Sell':>10}  #",
        "-" * 58,
    ]
    for day in result.days or ():
        top = day.top_ticker or "—"
        lines.append(
            f"{day.date.isoformat():12}  {top:6}  "
            f"{format_value(day.net_value):>10}  "
            f"{format_value(day.buy_value):>10}  "
            f"{format_value(day.sell_value):>10}  {day.ticker_count}"
        )
    if not result.days:
        lines.append("  —")
    lines.append("")
    lines.append(f"CLI: saham view broker calendar {result.broker_code}")
    return "\n".join(lines)


def _fmt_avg_buy(avg) -> str:
    if avg is None:
        return "—"
    # Prices are typically whole IDR; show compact integer when whole
    if avg == avg.to_integral_value():
        return f"@ {int(avg):,}"
    return f"@ {avg:,.2f}"


def format_desk_top_matrix_text(result) -> str:
    """Plain-text multi-window top-5 net-buy matrix (CLI + TUI).

    Cell: ticker · streak · net (partial mark) · avg buy.
    """
    wins = tuple(result.windows)
    lines = [
        f"Desk Top Matrix · {result.broker_code} ({result.broker_name})",
        (
            f"type {_type_label(result.broker_type)} · as of {result.as_of} · "
            f"sessions cached {result.sessions_cached}"
        ),
        str(result.scope_note),
        "cell: ticker · streak · net · avg buy · *partial = sessions < window",
        "",
    ]
    # Column headers
    header = f"{'#':>2}"
    for w in wins:
        header += f"  |  {w}s".ljust(28)
    lines.append(header.rstrip())
    lines.append("-" * min(120, 4 + 28 * len(wins)))

    max_rows = max((len(result.columns.get(w) or ()) for w in wins), default=0)
    if max_rows == 0:
        lines.append("  — no net-buy names in windows")
    for rank in range(max_rows):
        row = f"{rank + 1:>2}"
        for w in wins:
            col = result.columns.get(w) or ()
            if rank >= len(col):
                row += f"  |  {'—':26}"
                continue
            cell = col[rank]
            net_s = format_netx_display(
                cell.net_value,
                sessions_used=cell.sessions_used,
                window=cell.window,
            )
            # compact cell block on one line
            chunk = f"{cell.ticker} {cell.buy_streak}s {net_s} {_fmt_avg_buy(cell.avg_buy_price)}"
            row += f"  |  {chunk[:26]:26}"
        lines.append(row)

    lines.append("")
    lines.append(f"CLI: saham view broker top-matrix {result.broker_code}")
    return "\n".join(lines)
