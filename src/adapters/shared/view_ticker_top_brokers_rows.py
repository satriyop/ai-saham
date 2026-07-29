"""Stock→desks row builders (TUI table + multi-session NetX display).

Ranking/fallback policy: ViewTickerTopBrokersUseCase only.
Multi-session pulse: desk_session_pulse (application pure).

Layer: Adapter (shared pure presentation)
"""

from __future__ import annotations

from src.adapters.shared.view_number_format import format_value
from src.application.services.broker_desk_from_daily_flow import STOCK_DESK_NET_WINDOWS

# Display NetX windows for stock→desks (must match STOCK_DESK_NET_WINDOWS).
STOCK_DESK_DISPLAY_NET_WINDOWS: tuple[int, ...] = STOCK_DESK_NET_WINDOWS

# Partial NetX marker: value*(used/window) when sessions_cached < X.
PARTIAL_NETX_LEGEND = "* NetX partial — sum of cached sessions only (not full window)"


def _type_label_for_broker(broker) -> str:
    from src.domain.entities.broker_flow import BrokerType

    btype = getattr(broker, "broker_type", None)
    if btype == BrokerType.FOREIGN:
        return "Foreign"
    if btype == BrokerType.LOCAL:
        return "Local"
    return "Foreign" if getattr(broker, "is_foreign", False) else "Local"


def format_netx_display(value, *, sessions_used: int, window: int) -> str:
    """Format NetX; warn clearly when history is shorter than the window.

    Full window: ``1.20B``
    Partial:     ``60.00M*(4/20)``  (4 sessions cached, window wanted 20)
    """
    if value is None:
        return "—"
    base = format_value(value)
    used = int(sessions_used or 0)
    win = int(window)
    if used <= 0:
        return "—"
    if used < win:
        return f"{base}*({used}/{win})"
    return base


def _pulse_fields(pulse, *, net_windows: tuple[int, ...] = STOCK_DESK_DISPLAY_NET_WINDOWS) -> dict:
    """Map DeskSessionPulse → DayNet companion fields (NetX / Stk / Δ1)."""
    empty_nets = {f"net{w}": "—" for w in net_windows}
    if pulse is None:
        return {
            **empty_nets,
            "streak": "—",
            "delta1": "—",
            "sessions_in_net5": 0,
            "has_partial_netx": False,
            "partial_windows": (),
            "sessions_cached": 0,
        }
    delta1_s = "—"
    if pulse.delta1 is not None:
        sign = "+" if pulse.delta1 > 0 else ""
        delta1_s = f"{sign}{format_value(pulse.delta1)}"
    nets: dict[str, str] = {}
    partial_windows: list[int] = []
    sessions_cached = 0
    for w in net_windows:
        used = int(pulse.sessions_for(w) or 0)
        sessions_cached = max(sessions_cached, used)
        nets[f"net{w}"] = format_netx_display(
            pulse.net_for(w),
            sessions_used=used,
            window=w,
        )
        if 0 < used < w:
            partial_windows.append(w)
    return {
        **nets,
        "streak": str(pulse.buy_streak),
        "delta1": delta1_s,
        "sessions_in_net5": int(getattr(pulse, "sessions_in_net5", 0) or 0),
        "has_partial_netx": bool(partial_windows),
        "partial_windows": tuple(partial_windows),
        "sessions_cached": sessions_cached,
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
    map broker_code → DeskSessionPulse for stock-scoped multi-session NetX.
    Incomplete NetX (sessions < X) is labeled ``value*(used/X)`` — never silent.
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
            "has_partial_netx": pf["has_partial_netx"],
            "partial_windows": pf["partial_windows"],
            "sessions_cached": pf["sessions_cached"],
        }
        for w in net_windows:
            row_kw[f"net{w}"] = pf[f"net{w}"]
        return SimpleNamespace(**row_kw)

    for b in buyers:
        rows.append(_row(b, "buy"))
    for s in sellers:
        rows.append(_row(s, "sell"))
    return rows
