"""Present-only Rich cell markup for TUI boards (OpenCode visual bible).

No scoring, no IO. Maps plain board strings → OpenCode chips / heat.
Tokens: docs/design/tui-cockpit-opencode.md (mock .app palette).

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

# OpenCode semantic tokens
_MINT = "#6fbf8a"
_MINT_BG = "#121a14"
_BRASS = "#d4b06a"
_BRASS_BG = "#1a1810"
_CORAL = "#c97a72"
_CORAL_BG = "#1a1212"
_FOG = "#e8e8e8"
_MIST = "#7a7a7a"
_ASH = "#555555"
_TICKER = "#e8e8e8"
_LIFT = "#141414"
_PEACH = "#c9a68a"


def format_accum_board_cells(row: Any) -> tuple[Text | str, ...]:
    """Cells for accum board columns (1:1 BOARD_COLUMN_LABELS order)."""
    ticker = str(getattr(row, "ticker", "?") or "?")
    signal = str(getattr(row, "signal", "—") or "—")
    accum = str(getattr(row, "accum", "—") or "—")
    action = str(getattr(row, "action", "—") or "—")
    phase = str(getattr(row, "phase", "—") or "—")
    streak = str(getattr(row, "streak", "—") or "—")
    rsi = str(getattr(row, "rsi", "—") or "—")
    net = str(getattr(row, "net_pct", "—") or "—")
    disc = str(getattr(row, "disc_pct", "—") or "—")
    price = str(getattr(row, "price", "—") or "—")
    gate = str(getattr(row, "gate", "—") or "—")
    return (
        format_ticker_cell(ticker),
        format_signal_cell(signal),
        format_plain_num(accum),
        format_action_cell(action),
        format_phase_cell(phase),
        format_plain_num(streak),
        format_plain_num(rsi),
        format_net_cell(net),
        format_plain_num(disc),
        format_plain_num(price),
        format_gate_cell(gate),
    )


def format_ticker_cell(ticker: str) -> Text:
    t = (ticker or "?").strip() or "?"
    return Text(t, style=f"bold {_TICKER}")


def format_signal_cell(signal: str) -> Text:
    """Signal heat: high mint · mid brass · low mist (presentation bands only)."""
    s = (signal or "—").strip() or "—"
    band = signal_heat_band(s)
    if band == "hi":
        return Text(s, style=f"bold {_MINT}")
    if band == "mid":
        return Text(s, style=f"bold {_BRASS}")
    if band == "lo":
        return Text(s, style=_MIST)
    return Text(s, style=_ASH)


def signal_heat_band(signal: str) -> str:
    """Return hi|mid|lo|na from display string (not a re-score)."""
    try:
        v = float(str(signal).replace(",", "").strip())
    except (TypeError, ValueError):
        return "na"
    if v >= 80:
        return "hi"
    if v >= 70:
        return "mid"
    return "lo"


def format_action_cell(action: str) -> Text:
    a = (action or "—").strip() or "—"
    u = a.upper()
    if u in {"ENTER", "BUY"}:
        return Text(f" {u} ", style=f"bold {_MINT} on {_MINT_BG}")
    if u in {"WATCH", "HOLD"}:
        return Text(f" {u} ", style=f"bold {_BRASS} on {_BRASS_BG}")
    if u in {"AVOID", "BLOCK", "SELL"}:
        return Text(f" {u} ", style=f"bold {_CORAL} on {_CORAL_BG}")
    return Text(f" {a} ", style=_MIST)


def format_gate_cell(gate: str) -> Text:
    g = (gate or "—").strip() or "—"
    u = g.upper()
    if u in {"OPEN", "PASS", "CLEAR"}:
        return Text(u, style=f"bold {_MINT}")
    if u in {"BLOCK", "BLOCKED", "FAIL", "CLOSED"}:
        return Text(u, style=f"bold {_CORAL}")
    return Text(g, style=_MIST)


def format_phase_cell(phase: str) -> Text:
    p = (phase or "—").strip() or "—"
    return Text(f" {p} ", style=f"{_MIST} on {_LIFT}")


def format_plain_num(value: str) -> Text:
    s = (value or "—").strip() or "—"
    return Text(s, style=_FOG)


def format_net_cell(net: str) -> Text:
    """Tint net% sign when parseable (presentation only)."""
    s = (net or "—").strip() or "—"
    try:
        v = float(s.replace("%", "").replace(",", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return Text(s, style=_FOG)
    if v > 0:
        return Text(s, style=_MINT)
    if v < 0:
        return Text(s, style=_CORAL)
    return Text(s, style=_FOG)


def format_preopen_grade_cell(grade: str) -> Text:
    g = (grade or "—").strip() or "—"
    u = g.upper()
    if u == "A":
        return Text(u, style=f"bold {_MINT}")
    if u == "B":
        return Text(u, style="bold #7aa2c4")
    if u == "C":
        return Text(u, style=f"bold {_BRASS}")
    return Text(g, style=_MIST)


def format_preopen_risk_cell(risk: str) -> Text:
    r = (risk or "—").strip() or "—"
    u = r.upper()
    if u in {"CLEAR", "OPEN", "PASS"}:
        return Text(r, style=f"bold {_MINT}")
    if u in {"BLOCK", "BLOCKED", "FAIL"}:
        return Text(r, style=f"bold {_CORAL}")
    if u in {"WATCH", "WARN"}:
        return Text(r, style=f"bold {_BRASS}")
    return Text(r, style=_MIST)


def format_preopen_delta_cell(delta: str) -> Text:
    """Signed Δ% heat for pre-open board (presentation only)."""
    return format_net_cell(delta)


def format_preopen_board_cells(row: Any) -> tuple[Text | str, ...]:
    """Cells for pre-open contract: Tkr IEP Δ% IEV NCP ΔIEV Grd Risk."""
    return (
        format_ticker_cell(str(getattr(row, "ticker", "?") or "?")),
        format_plain_num(str(getattr(row, "iep", "—") or "—")),
        format_preopen_delta_cell(str(getattr(row, "delta_pct", "—") or "—")),
        format_plain_num(str(getattr(row, "iev", "—") or "—")),
        format_plain_num(str(getattr(row, "ncp", "—") or "—")),
        format_preopen_delta_cell(str(getattr(row, "delta_iev", "—") or "—")),
        format_preopen_grade_cell(str(getattr(row, "grade", "—") or "—")),
        format_preopen_risk_cell(str(getattr(row, "risk", "—") or "—")),
    )


def format_signed_flow_cell(value: str) -> Text:
    """Tint DayNet / Net5 / Δ1 strings that look like +12.3B / −1.2M."""
    s = (value or "—").strip() or "—"
    if s in {"—", "-", ""}:
        return Text(s, style=_ASH)
    if s.startswith("+"):
        return Text(s, style=_MINT)
    if s.startswith("-") or s.startswith("−"):
        return Text(s, style=_CORAL)
    cleaned = (
        s.replace(",", "")
        .replace("B", "")
        .replace("M", "")
        .replace("K", "")
        .replace("%", "")
        .replace("−", "-")
        .strip()
    )
    try:
        v = float(cleaned)
    except (TypeError, ValueError):
        return Text(s, style=_FOG)
    if v > 0:
        return Text(s, style=_MINT)
    if v < 0:
        return Text(s, style=_CORAL)
    return Text(s, style=_FOG)


def format_broker_list_cells(row: Any) -> tuple[Text | str, ...]:
    """Broker list contract: Code Type AsOf DayNet Net5 Stk Δ1 # Top."""
    return (
        format_ticker_cell(str(getattr(row, "code", "?") or "?")),
        Text(str(getattr(row, "type_label", "—") or "—"), style=_MIST),
        format_plain_num(str(getattr(row, "as_of", "—") or "—")),
        format_signed_flow_cell(str(getattr(row, "day_net", "—") or "—")),
        format_signed_flow_cell(str(getattr(row, "net5", "—") or "—")),
        format_plain_num(str(getattr(row, "streak", "—") or "—")),
        format_signed_flow_cell(str(getattr(row, "delta1", "—") or "—")),
        format_plain_num(str(getattr(row, "tickers", "—") or "—")),
        Text(str(getattr(row, "top_buy", "—") or "—"), style=_FOG),
    )


def format_triage_markup(summary: str) -> str:
    """Color Action tokens inside board summary for meta/status (Textual markup)."""
    if not summary:
        return ""
    out = summary
    for token, color in (
        ("ENTER", _MINT),
        ("WATCH", _BRASS),
        ("AVOID", _CORAL),
        ("OPEN", _MINT),
        ("BLOCK", _CORAL),
        ("BLOCKED", _CORAL),
    ):
        out = out.replace(token, f"[{color}]{token}[/]")
    return out
