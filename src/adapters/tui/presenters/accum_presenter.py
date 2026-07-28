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


# ── Focus strip (P0 why-action · P1 Accum recipe · P2 lag) ─


@dataclass(frozen=True)
class AccumFocusView:
    """Multi-line focus strip + sidebar lag for one selected row."""

    strip: str
    lag_label: str
    focus_sidebar: str


def build_accum_focus(
    row: AccumRowView,
    *,
    rank: int = 1,
    total: int = 1,
) -> AccumFocusView:
    """Build honest focus text: action reasons, Accum recipe, data lag."""
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
    why = _action_why(source, gate=gate)
    recipe = _accum_recipe(source, accum_display=accum)
    disc_note = _disc_gloss(source, disc_pct)

    line1 = (
        f"[#9b8fb8]Focus · {ticker}[/]  "
        f"#{rank}/{total} by Signal  ·  "
        f"Signal {signal} · Accum {accum} · "
        f"{action} · gate {gate}"
    )
    line2 = f"[#d4b06a]Why {action}[/]  {why}" if why else f"Why {action}  —"
    line3 = f"[#9b8fb8]Accum recipe[/]  {recipe}"
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

    return AccumFocusView(strip=strip, lag_label=lag or "—", focus_sidebar=sidebar)


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


def _action_why(candidate: Any, *, gate: str) -> str:
    """P0: why Action is not a clean enter despite scores/gates."""
    if candidate is None:
        return ""
    bits: list[str] = []

    # Coverage
    cov = _coverage_pct(candidate)
    if cov is not None:
        if cov < 70.0:
            bits.append(f"authority {cov:.0f}% (<70%)")
        else:
            bits.append(f"authority {cov:.0f}%")

    # Decision constraints from Signal assessment
    sa = getattr(candidate, "signal_assessment", None)
    assessment = getattr(sa, "assessment", None) if sa is not None else None
    constraints = getattr(assessment, "decision_constraints", None) if assessment else None
    if constraints is not None:
        for reason in getattr(constraints, "constraint_reasons", ()) or ():
            text = str(reason)
            # Compress long engine phrases
            low = text.lower()
            if "signal_authority_coverage" in low or "authority_coverage" in low:
                if not any("authority" in b for b in bits):
                    bits.append("authority thin")
                continue
            if "setup readiness" in low or "setup_readiness" in low:
                bits.append("setup readiness unavailable")
                continue
            if "caps" in low or "cap" in low:
                bits.append(text if len(text) < 48 else text[:45] + "…")
                continue
            if text and text not in bits:
                bits.append(text if len(text) < 52 else text[:49] + "…")

    # Setup readiness object if present
    readiness = getattr(assessment, "setup_readiness", None) if assessment else None
    if readiness is None and sa is not None:
        readiness = getattr(sa, "setup_readiness", None)
    if readiness is not None:
        status = getattr(readiness, "status", None)
        status_s = str(getattr(status, "value", status) or "")
        if status_s and "UNAVAILABLE" in status_s.upper():
            if not any("setup readiness" in b for b in bits):
                bits.append("setup readiness unavailable")

    # Gate
    if gate == "BLOCKED":
        risk = getattr(candidate, "risk_assessment", None)
        which = getattr(risk, "gate_triggered", None) if risk else None
        bits.append(f"gate blocked ({which})" if which else "gate blocked")
    elif gate == "OPEN":
        bits.append("gate open")

    # Coverage warning string
    warn = getattr(sa, "coverage_warning", None) if sa is not None else None
    if warn and cov is not None and cov < 70:
        # already have authority bit
        pass

    if not bits:
        ts = getattr(candidate, "trade_setup", None)
        rat = getattr(ts, "rationale", None) if ts else None
        if rat:
            return str(rat)[:80]
        return "no constraint detail"
    return " · ".join(bits)


def _coverage_pct(candidate: Any) -> float | None:
    sa = getattr(candidate, "signal_assessment", None)
    if sa is None:
        return None
    assessment = getattr(sa, "assessment", None)
    raw = None
    if assessment is not None:
        raw = getattr(assessment, "signal_authority_coverage", None)
    if raw is None:
        raw = getattr(sa, "signal_authority_coverage", None)
    if isinstance(raw, (int, float)):
        # Engine may store 0–1 or 0–100
        val = float(raw)
        return val * 100.0 if val <= 1.0 else val
    return None


def _accum_recipe(candidate: Any, *, accum_display: str) -> str:
    """P1: Accum total as sum of component points."""
    if candidate is None:
        return f"{accum_display} (no breakdown)"
    bd = getattr(candidate, "accum_score_breakdown", None)
    if bd is None:
        return f"{accum_display} (no breakdown)"
    parts: list[str] = []
    for comp in getattr(bd, "components", ()) or ():
        key = getattr(comp, "key", "?")
        status = getattr(comp, "status", None)
        status_s = str(getattr(status, "value", status) or "")
        if status_s == "DISABLED":
            parts.append(f"{key} off")
            continue
        if status_s == "MISSING":
            parts.append(f"{key} miss")
            continue
        pts = getattr(comp, "score_points", None)
        if pts is None:
            parts.append(f"{key} —")
        else:
            parts.append(f"{key} {float(pts):.1f}")
    if not parts:
        return f"{accum_display}"
    return f"{accum_display} = " + " + ".join(parts)


def _disc_gloss(candidate: Any, disc_display: str) -> str:
    if candidate is None:
        return f"disc {disc_display}"
    disc = getattr(candidate, "vwap_discount_pct", None)
    if isinstance(disc, Decimal):
        disc = float(disc)
    if not isinstance(disc, (int, float)):
        return f"disc {disc_display}"
    if disc < 0:
        return f"disc {disc_display} (above F_VWAP → vwap pts 0)"
    if disc == 0:
        return f"disc {disc_display} (at F_VWAP)"
    return f"disc {disc_display} (under F_VWAP)"
