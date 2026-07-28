"""Present accumulation workflow result as CLI-faithful desk board (option B).

Columns: Ticker | Signal | Accum | Action | Phase | Streak | RSI | Net% | Disc% | Price | Gate

Labels follow ADR-043 (Accum vs Signal never collapsed into generic "Score").

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.shared.decision_display import (
    format_accum_breakdown,
    format_action_why,
)
from src.adapters.shared.screen_accum_board_fields import (
    BOARD_COLUMN_LABELS,
    extract_screen_accum_board_fields,
)

# Re-export for callers that imported from this module historically.
__all__ = (
    "AccumBoardView",
    "AccumFocusView",
    "AccumPresenter",
    "AccumRowView",
    "build_accum_focus",
    "format_accum_breakdown",
)


@dataclass(frozen=True)
class AccumRowView:
    ticker: str
    signal: str
    accum: str
    action: str
    phase: str
    streak: str
    rsi: str
    net_pct: str
    disc_pct: str
    price: str
    gate: str
    name: str = ""
    source: Any = None


@dataclass(frozen=True)
class AccumBoardView:
    rows: tuple[AccumRowView, ...]
    meta: str
    cache_label: str
    # One-line triage after load (counts only — no new scoring)
    summary: str = ""
    # Header labels for DataTable (ADR-043 vocabulary)
    columns: tuple[str, ...] = BOARD_COLUMN_LABELS


class AccumPresenter:
    def present(self, payload: Any) -> AccumBoardView:
        projection = _unwrap_single_projection(payload)
        candidates = list(getattr(projection, "candidates", ()) or [])
        rows = tuple(_row(c) for c in candidates)

        window = getattr(projection, "window_days", None) or 7
        sort_by = "signal"
        applied = getattr(projection, "applied_filters", None)
        if applied is not None:
            sort_by = str(getattr(applied, "sort_by", None) or sort_by)
            top = getattr(applied, "top", None)
        else:
            top = len(rows)

        as_of = ""
        data_as_of = getattr(projection, "data_as_of", None) or {}
        if isinstance(data_as_of, dict):
            as_of = (
                data_as_of.get("latest_candle_date")
                or data_as_of.get("as_of")
                or data_as_of.get("latest_broker_date")
                or ""
            )

        meta_bits = [
            f"sort {sort_by} (not Accum)",
            f"window {window}d",
            f"top {top if top is not None else len(rows)}",
            f"{len(rows)} names",
        ]
        if as_of:
            meta_bits.insert(0, f"as of {as_of}")
        lag = _board_lag_label(candidates)
        if lag:
            meta_bits.append(lag)
        cache = lag if lag else (f"local · {as_of}" if as_of else "local")
        summary = _board_summary(rows)
        return AccumBoardView(
            rows=rows,
            meta=" · ".join(meta_bits),
            cache_label=cache,
            summary=summary,
        )


def _unwrap_single_projection(payload: Any) -> Any:
    if payload is None:
        return payload
    single = getattr(payload, "single_projection", None)
    if single is not None:
        return single
    if hasattr(payload, "candidates"):
        return payload
    return payload


def _row(candidate: Any) -> AccumRowView:
    fields = extract_screen_accum_board_fields(candidate, phase_style="short")
    name = str(getattr(candidate, "name", "") or getattr(candidate, "company_name", "") or "")
    return AccumRowView(
        ticker=fields.ticker,
        signal=fields.signal,
        accum=fields.accum,
        action=fields.action,
        phase=fields.phase,
        streak=fields.streak,
        rsi=fields.rsi,
        net_pct=fields.net_pct,
        disc_pct=fields.disc_pct,
        price=fields.price,
        gate=fields.gate,
        name=name,
        source=candidate,
    )


# ── Focus strip (why Action · Accum breakdown · lag) ───────


@dataclass(frozen=True)
class AccumFocusView:
    """Multi-line focus strip + sidebar lag for one selected row."""

    strip: str
    lag_label: str
    focus_sidebar: str
    why: str = ""


def build_accum_focus(
    row: AccumRowView,
    *,
    rank: int = 1,
    total: int = 1,
) -> AccumFocusView:
    """Build honest focus text: action reasons, Accum breakdown, data lag."""
    source = getattr(row, "source", None)
    ticker = str(getattr(row, "ticker", "?"))
    signal = str(getattr(row, "signal", "—"))
    accum = str(getattr(row, "accum", "—"))
    action = str(getattr(row, "action", "—"))
    gate = str(getattr(row, "gate", "—"))
    phase = str(getattr(row, "phase", "—"))
    streak = str(getattr(row, "streak", "—"))
    net_pct = str(getattr(row, "net_pct", "—"))
    disc_pct = str(getattr(row, "disc_pct", "—"))
    price = str(getattr(row, "price", "—"))

    lag = _lag_from_candidate(source)
    why = format_action_why(source, gate=gate)
    breakdown = format_accum_breakdown(source, accum_display=accum)
    disc_note = _disc_gloss(source, disc_pct)

    line1 = (
        f"[#9b8fb8]Focus · {ticker}[/]  "
        f"#{rank}/{total} by Signal  ·  "
        f"Signal {signal} · Accum {accum} · "
        f"{action} · gate {gate}"
    )
    line2 = f"[#d4b06a]Why {action}[/]  {why}" if why else f"Why {action}  —"
    line3 = f"[#9b8fb8]Accum breakdown[/]  {breakdown}"
    line4_bits = [f"phase {phase}", f"streak {streak}", f"net {net_pct}"]
    if disc_note:
        line4_bits.append(disc_note)
    else:
        line4_bits.append(f"disc {disc_pct}")
    line4_bits.append(f"px {price}")
    if lag:
        line4_bits.append(lag)
    line4 = " · ".join(line4_bits)

    strip = "\n".join([line1, line2, line3, line4])
    if why:
        short_why = why if len(why) <= 42 else why[:39] + "…"
        sidebar = f"{ticker} · {action}\n{short_why}"
    else:
        sidebar = f"{ticker} · Enter view · p plan"

    return AccumFocusView(
        strip=strip,
        lag_label=lag or "—",
        focus_sidebar=sidebar,
        why=why,
    )


def _board_summary(rows: tuple[AccumRowView, ...]) -> str:
    """Triage counts for the loaded board (presentation only)."""
    if not rows:
        return "0 names"
    n = len(rows)
    by_action: dict[str, int] = {}
    by_gate: dict[str, int] = {}
    for row in rows:
        a = str(getattr(row, "action", "—") or "—")
        g = str(getattr(row, "gate", "—") or "—")
        by_action[a] = by_action.get(a, 0) + 1
        by_gate[g] = by_gate.get(g, 0) + 1
    # Prefer stable order: common action labels first, then rest
    action_items = sorted(by_action.items(), key=lambda kv: (-kv[1], kv[0]))
    gate_items = sorted(by_gate.items(), key=lambda kv: (-kv[1], kv[0]))
    action_parts = [f"{k} {v}" for k, v in action_items]
    gate_parts = [f"{k} {v}" for k, v in gate_items]
    return f"{n} names · Action: {', '.join(action_parts)} · Gate: {', '.join(gate_parts)}"


def _board_lag_label(candidates: list[Any]) -> str:
    if not candidates:
        return ""
    # Prefer first row freshness (same session for board)
    return _lag_from_candidate(candidates[0])


def _lag_from_candidate(candidate: Any) -> str:
    if candidate is None:
        return ""
    fr = getattr(candidate, "freshness", None)
    candle = getattr(candidate, "latest_candle_date", None)
    broker = getattr(candidate, "latest_broker_date", None)
    align = None
    if fr is not None:
        candle = getattr(fr, "candle_as_of", None) or candle
        broker = getattr(fr, "broker_as_of", None) or broker
        align = getattr(fr, "alignment_state", None)
    if candle is None and broker is None:
        return ""
    c_s = str(candle) if candle is not None else "—"
    b_s = str(broker) if broker is not None else "—"
    # Short dates if ISO
    if len(c_s) >= 10:
        c_s = c_s[5:10] if c_s[4:5] == "-" else c_s  # MM-DD-ish from YYYY-MM-DD
    if len(b_s) >= 10 and b_s[4:5] == "-":
        b_s = b_s[5:10]
    align_s = ""
    if align is not None:
        align_s = str(getattr(align, "value", align))
    if align_s:
        return f"candle {c_s} · broker {b_s} · {align_s}"
    return f"candle {c_s} · broker {b_s}"


def _disc_gloss(candidate: Any, disc_display: str) -> str:
    if candidate is None:
        return f"disc {disc_display}"
    disc = getattr(candidate, "vwap_discount_pct", None)
    try:
        if disc is not None:
            disc = float(disc)
    except (TypeError, ValueError):
        disc = None
    if not isinstance(disc, (int, float)):
        return f"disc {disc_display}"
    if disc < 0:
        return f"disc {disc_display} (above F_VWAP → vwap pts 0)"
    if disc == 0:
        return f"disc {disc_display} (at F_VWAP)"
    return f"disc {disc_display} (under F_VWAP)"
