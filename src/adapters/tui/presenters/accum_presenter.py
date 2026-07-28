"""Present accumulation workflow result as CLI-faithful desk board (option B).

Columns: Ticker | Signal | Accum | Action | Phase | Streak | RSI | Net% | Disc% | Price | Gate

Labels follow ADR-043 (Accum vs Signal never collapsed into generic "Score").

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.score_display_labels import ACCUM, SIGNAL
from src.adapters.shared.vwap_depth_display import format_disc_pct_plain

# Short phase labels aligned with CLI screen_accum_formatters._PHASE_LABELS
_PHASE_SHORT = {
    "NONE": "NONE",
    "ACCUMULATION": "ACCUM",
    "COMPRESSION": "COMPRESS",
    "BREAKOUT_CONFIRMATION": "BREAKOUT",
    "EXHAUSTION": "EXHAUST",
    "DISTRIBUTION": "DISTRIB",
    "FAILED": "FAILED",
}


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
    # Header labels for DataTable (ADR-043 vocabulary)
    columns: tuple[str, ...] = (
        "Ticker",
        SIGNAL,
        ACCUM,
        "Action",
        "Phase",
        "Streak",
        "RSI",
        "Net%",
        "Disc%",
        "Price",
        "Gate",
    )


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
            f"sort {sort_by}",
            f"window {window}d",
            f"top {top if top is not None else len(rows)}",
            f"{len(rows)} names",
        ]
        if as_of:
            meta_bits.insert(0, f"as of {as_of}")
        cache = f"local · {as_of}" if as_of else "local"
        return AccumBoardView(rows=rows, meta=" · ".join(meta_bits), cache_label=cache)


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
    ticker = str(getattr(candidate, "ticker", "?"))

    signal = _signal_score(candidate)
    accum = _accum_score(candidate)
    action = _action_label(candidate)
    phase = _phase_label(candidate)
    streak = _streak(candidate)
    rsi = _rsi(candidate)
    net_pct = _net_pct(candidate)
    disc_pct = _disc_pct(candidate)
    price = _price(candidate)
    gate = _gate_label(candidate)
    name = str(getattr(candidate, "name", "") or getattr(candidate, "company_name", "") or "")

    return AccumRowView(
        ticker=ticker,
        signal=signal,
        accum=accum,
        action=action,
        phase=phase,
        streak=streak,
        rsi=rsi,
        net_pct=net_pct,
        disc_pct=disc_pct,
        price=price,
        gate=gate,
        name=name,
        source=candidate,
    )


def _signal_score(candidate: Any) -> str:
    sa = getattr(candidate, "signal_assessment", None)
    if sa is None:
        return "—"
    assessment = getattr(sa, "assessment", None)
    if assessment is None:
        raw = getattr(sa, "score", None)
    else:
        raw = getattr(assessment, "score", None)
    if isinstance(raw, (int, float)):
        return f"{int(raw)}"
    return "—"


def _accum_score(candidate: Any) -> str:
    accum = getattr(candidate, "accum_score", None)
    if isinstance(accum, (int, float)):
        return f"{float(accum):.1f}"
    return "—"


def _action_label(candidate: Any) -> str:
    trade_setup = getattr(candidate, "trade_setup", None)
    if trade_setup is None:
        return "—"
    action = getattr(trade_setup, "action", None)
    if action is None:
        return "—"
    # Prefer product short label on the enum; never invent pass/watch/block.
    short = getattr(action, "short", None)
    if short:
        return str(short)
    return str(getattr(action, "value", action))


def _phase_label(candidate: Any) -> str:
    phase = getattr(candidate, "setup_phase", None)
    if phase is None:
        return "—"
    current = getattr(phase, "current_phase", None)
    if current is None:
        return "—"
    raw = str(getattr(current, "value", current))
    return _PHASE_SHORT.get(raw, raw[:8] if len(raw) > 8 else raw)


def _streak(candidate: Any) -> str:
    streak = getattr(candidate, "consecutive_streak", None)
    if isinstance(streak, int):
        return str(streak)
    if isinstance(streak, float):
        return str(int(streak))
    return "—"


def _rsi(candidate: Any) -> str:
    rsi_val = getattr(candidate, "rsi", None)
    if rsi_val is None:
        rsi_val = getattr(candidate, "rsi_14", None)
    if isinstance(rsi_val, Decimal):
        return f"{float(rsi_val):.1f}"
    if isinstance(rsi_val, (int, float)):
        return f"{float(rsi_val):.1f}"
    return "—"


def _net_pct(candidate: Any) -> str:
    ratio = getattr(candidate, "net_buy_ratio", None)
    if isinstance(ratio, (int, float)):
        return f"{float(ratio) * 100:.0f}%"
    return "—"


def _disc_pct(candidate: Any) -> str:
    disc = getattr(candidate, "vwap_discount_pct", None)
    if isinstance(disc, Decimal):
        disc = float(disc)
    if isinstance(disc, (int, float)):
        # Compact for table: sign+pct only (depth badge is long for narrow cols)
        return f"{float(disc):+.1f}%"
    plain = format_disc_pct_plain(None)
    return plain


def _price(candidate: Any) -> str:
    price = getattr(candidate, "current_price", None)
    if price is None:
        return "—"
    try:
        return f"{int(float(price)):,}"
    except (TypeError, ValueError):
        return str(price)


def _gate_label(candidate: Any) -> str:
    risk = getattr(candidate, "risk_assessment", None)
    if risk is None:
        return "—"
    triggered = getattr(risk, "gate_triggered", None)
    if triggered:
        return "BLOCKED"
    return "OPEN"
