"""Present accumulation workflow result as CLI-faithful desk board (option B).

Columns: Ticker | Signal | Accum | Action | Phase | Streak | RSI | Net% | Disc% | Price | Gate

Labels follow ADR-043 (Accum vs Signal never collapsed into generic "Score").

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.shared.screen_accum_board_fields import (
    BOARD_COLUMN_LABELS,
    extract_screen_accum_board_fields,
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

    sa = getattr(candidate, "signal_assessment", None)
    assessment = getattr(sa, "assessment", None) if sa is not None else None

    # Typed setup readiness first (concrete missing inputs / failed requirements).
    readiness = getattr(assessment, "setup_readiness", None) if assessment else None
    if readiness is None and sa is not None:
        readiness = getattr(sa, "setup_readiness", None)
    readiness_bit = _setup_readiness_detail(readiness)
    if readiness_bit:
        bits.append(readiness_bit)

    # Decision constraints — skip phrases already covered by structured fields.
    constraints = getattr(assessment, "decision_constraints", None) if assessment else None
    if constraints is not None:
        for reason in getattr(constraints, "constraint_reasons", ()) or ():
            text = str(reason)
            low = text.lower()
            if "signal_authority_coverage" in low or "authority_coverage" in low:
                if not any(b.startswith("authority") for b in bits):
                    bits.append("authority thin")
                continue
            if "setup readiness" in low or "setup_readiness" in low:
                # Prefer structured readiness_bit; only fall back if absent.
                if not any(b.startswith("setup readiness") for b in bits):
                    bits.append(_fallback_setup_readiness_phrase(text))
                continue
            if text and text not in bits:
                bits.append(text if len(text) < 52 else text[:49] + "…")

    # Gate
    if gate == "BLOCKED":
        risk = getattr(candidate, "risk_assessment", None)
        which = getattr(risk, "gate_triggered", None) if risk else None
        bits.append(f"gate blocked ({which})" if which else "gate blocked")
    elif gate == "OPEN":
        bits.append("gate open")

    if not bits:
        ts = getattr(candidate, "trade_setup", None)
        rat = getattr(ts, "rationale", None) if ts else None
        if rat:
            return str(rat)[:80]
        return "no constraint detail"
    return " · ".join(bits)


def _setup_readiness_detail(readiness: Any) -> str:
    """Concrete setup-readiness line: status + missing/failed inputs."""
    if readiness is None:
        return ""
    status = getattr(readiness, "status", None)
    status_s = str(getattr(status, "value", status) or "").upper()
    if not status_s or status_s == "READY":
        return ""

    missing = tuple(getattr(readiness, "missing_required_inputs", ()) or ())
    failed = tuple(getattr(readiness, "failed_requirements", ()) or ())
    family = getattr(readiness, "setup_family", None)
    family_s = f" [{family}]" if family else ""

    if status_s == "UNAVAILABLE":
        if missing:
            miss = ", ".join(str(m) for m in missing[:5])
            if len(missing) > 5:
                miss += ", …"
            return f"setup readiness UNAVAILABLE{family_s} (missing: {miss})"
        return f"setup readiness UNAVAILABLE{family_s}"

    if status_s == "INCOMPLETE":
        if failed:
            fail = ", ".join(str(f) for f in failed[:4])
            return f"setup readiness INCOMPLETE{family_s} ({fail})"
        return f"setup readiness INCOMPLETE{family_s}"

    if status_s == "INELIGIBLE":
        if failed:
            fail = ", ".join(str(f) for f in failed[:4])
            return f"setup readiness INELIGIBLE{family_s} ({fail})"
        phase = getattr(readiness, "current_phase", None)
        phase_s = getattr(phase, "value", phase) if phase is not None else None
        if phase_s:
            return f"setup readiness INELIGIBLE{family_s} (phase {phase_s})"
        return f"setup readiness INELIGIBLE{family_s}"

    return f"setup readiness {status_s}{family_s}"


def _fallback_setup_readiness_phrase(constraint_text: str) -> str:
    """When VO is missing, compress constraint string without inventing inputs."""
    low = constraint_text.lower()
    if "unavailable" in low:
        return "setup readiness UNAVAILABLE"
    if "incomplete" in low:
        return "setup readiness INCOMPLETE"
    if "ineligible" in low:
        return "setup readiness INELIGIBLE"
    return constraint_text if len(constraint_text) < 52 else constraint_text[:49] + "…"


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
