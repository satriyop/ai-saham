"""Present pre-open screen response as dense board rows.

Locked columns (design authority § Pre-open):
  Tkr · Act · IEP · Δ% · IEV · NCP · ΔIEV · Risk

NCP = lock/phase flag (LOCK / disc / —), never intensity float.
ΔIEV = locked baseline delta when present, honest — when missing.
Act = TradeSetup Action when authoritative; else —.
Grd A/B/C is not a board column.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Locked board column labels (1:1 design contract).
PREOPEN_BOARD_COLUMN_LABELS: tuple[str, ...] = (
    "Tkr",
    "Act",
    "IEP",
    "Δ%",
    "IEV",
    "NCP",
    "ΔIEV",
    "Risk",
)


@dataclass(frozen=True)
class PreOpenRowView:
    ticker: str
    action: str
    iep: str
    delta_pct: str
    iev: str
    ncp: str
    delta_iev: str
    risk: str
    evidence: str = ""
    source: Any = None


@dataclass(frozen=True)
class PreOpenSessionStrip:
    """Four-cell session honesty strip above the board (not row metrics)."""

    source: str
    phase: str
    funnel: str
    window: str

    def as_meta_line(self) -> str:
        return f"{self.source} · {self.phase} · {self.funnel} · {self.window}"

    def as_title_suffix(self) -> str:
        return f"{self.source} · {self.phase}"


@dataclass(frozen=True)
class PreOpenBoardView:
    rows: tuple[PreOpenRowView, ...]
    meta: str
    cache_label: str
    session_strip: PreOpenSessionStrip | None = None
    columns: tuple[str, ...] = PREOPEN_BOARD_COLUMN_LABELS


class PreOpenPresenter:
    def present(self, payload: Any) -> PreOpenBoardView:
        candidates, snapshot_date, warnings, extras = _extract(payload)
        rows = tuple(_row(c, extras=extras) for c in candidates)
        strip = _session_strip(
            rows=rows,
            candidates=candidates,
            snapshot_date=snapshot_date,
            warnings=warnings,
            extras=extras,
            payload=payload,
        )
        meta_bits = [strip.as_meta_line()]
        if warnings:
            meta_bits.append(f"{len(warnings)} warn")
        cache = f"snapshot · {snapshot_date}" if snapshot_date else "local"
        return PreOpenBoardView(
            rows=rows,
            meta=" · ".join(meta_bits),
            cache_label=cache,
            session_strip=strip,
        )


def _extract(payload: Any) -> tuple[list[Any], str, list[str], dict[str, Any]]:
    if payload is None:
        return [], "", [], {}
    snapshot_date = str(getattr(payload, "snapshot_date", "") or "")
    if hasattr(snapshot_date, "isoformat"):
        snapshot_date = snapshot_date.isoformat()  # type: ignore[union-attr]
    warnings = list(getattr(payload, "warnings", ()) or [])
    response = getattr(payload, "response", payload)
    result = getattr(response, "result", response)
    candidates = list(getattr(result, "candidates", ()) or [])

    extras: dict[str, Any] = {
        "total_movers_seen": getattr(result, "total_movers_seen", None),
        "capture_phase": getattr(response, "capture_phase", None)
        or getattr(payload, "capture_phase", None),
        "ncp_authoritative": getattr(response, "ncp_authoritative", None)
        or getattr(payload, "ncp_authoritative", None),
        "source_is_live": getattr(response, "source_is_live", None)
        or getattr(payload, "source_is_live", None),
        "trade_setup_by_ticker": getattr(response, "trade_setup_by_ticker", None)
        or getattr(payload, "trade_setup_by_ticker", None),
        "risk_by_ticker": getattr(response, "risk_by_ticker", None)
        or getattr(payload, "risk_by_ticker", None),
        "signal_by_ticker": getattr(response, "signal_by_ticker", None)
        or getattr(payload, "signal_by_ticker", None),
    }
    return candidates, snapshot_date, warnings, extras


def _row(candidate: Any, *, extras: dict[str, Any]) -> PreOpenRowView:
    ticker = str(getattr(candidate, "ticker", "?"))
    iep_raw = getattr(candidate, "iep", None)
    iep = f"{int(iep_raw):,}" if isinstance(iep_raw, (int, float)) else "—"

    gap = getattr(candidate, "iep_gap_pct", None)
    if gap is None:
        gap = getattr(candidate, "gap_pct", None)
    if isinstance(gap, Decimal):
        gap_f = float(gap)
    elif isinstance(gap, (int, float)):
        gap_f = float(gap)
    else:
        gap_f = None
    if gap_f is None:
        delta = "—"
    else:
        delta = f"{gap_f:+.1f}"

    iev_raw = getattr(candidate, "iev", None)
    if isinstance(iev_raw, (int, float)):
        iev = _fmt_volume(iev_raw)
    else:
        iev = "—"

    action = _action(candidate, extras)
    ncp = _ncp_flag(candidate, extras)
    delta_iev = _locked_delta_iev(candidate)
    risk = _risk_annotate(candidate, extras)

    evidence = _evidence_line(
        candidate,
        action=action,
        ncp=ncp,
        delta_iev=delta_iev,
        delta=delta,
        iev=iev,
    )
    return PreOpenRowView(
        ticker=ticker,
        action=action,
        iep=iep,
        delta_pct=delta,
        iev=iev,
        ncp=ncp,
        delta_iev=delta_iev,
        risk=risk,
        evidence=evidence,
        source=candidate,
    )


def _action(candidate: Any, extras: dict[str, Any]) -> str:
    """TradeSetup Action only when authoritative; never invent ENTER/WATCH."""
    raw = getattr(candidate, "action", None)
    if raw is None:
        raw = getattr(candidate, "setup_action", None)
    if raw is not None:
        val = getattr(raw, "value", raw)
        s = str(val or "").strip()
        if s and s not in {"None", "—", "-"}:
            return s.upper() if s.isalpha() or "_" in s else s

    setups = extras.get("trade_setup_by_ticker") or {}
    ticker = str(getattr(candidate, "ticker", "") or "").upper()
    setup = setups.get(ticker) or setups.get(getattr(candidate, "ticker", ""))
    if setup is not None:
        act = getattr(setup, "action", None)
        if act is not None:
            val = getattr(act, "value", act)
            s = str(val or "").strip()
            if s and s not in {"None", "—", "-"}:
                return s
    return "—"


def _ncp_flag(candidate: Any, extras: dict[str, Any]) -> str:
    """Lock/phase flag only — never iev_intensity float."""
    # Explicit per-candidate lock
    for key in ("ncp_lock", "ncp_flag", "ncp_phase"):
        raw = getattr(candidate, key, None)
        if raw is not None and str(raw).strip() not in {"", "None"}:
            return _normalize_ncp_flag(str(raw))

    locked = getattr(candidate, "is_ncp_locked", None)
    if locked is True or locked == 1:
        return "LOCK"
    if locked is False or locked == 0:
        return "disc"

    # Payload-level capture authority
    ncp_auth = extras.get("ncp_authoritative")
    phase = str(extras.get("capture_phase") or "").upper()
    if ncp_auth is True or phase == "NCP_LOCKED":
        return "LOCK"
    if phase in {"PRE_NCP", "SNAPSHOT", "UNKNOWN", "DISCOVERY", "DISCOVERY_ONLY"}:
        return "disc"
    if ncp_auth is False:
        return "disc"
    # TUI snapshot path default: discovery honesty
    return "disc"


def _normalize_ncp_flag(raw: str) -> str:
    u = raw.strip().upper()
    if u in {"LOCK", "LOCKED", "NCP_LOCKED", "NCP-LOCKED"}:
        return "LOCK"
    if u in {"DISC", "DISCOVERY", "DISCOVERY-ONLY", "DISCOVERY_ONLY", "PRE_NCP"}:
        return "disc"
    if u in {"—", "-", "NONE", "NA", "N/A"}:
        return "—"
    # Reject intensity-like floats
    try:
        float(raw)
        return "—"
    except ValueError:
        pass
    if len(raw) <= 8:
        return raw
    return "—"


def _locked_delta_iev(candidate: Any) -> str:
    """Locked final − baseline only. Never copy intensity."""
    raw = getattr(candidate, "delta_iev", None)
    if raw is None:
        raw = getattr(candidate, "locked_delta_iev", None)
    if raw is None:
        return "—"
    if isinstance(raw, bool):
        return "—"
    if isinstance(raw, Decimal):
        raw = float(raw)
    if isinstance(raw, (int, float)):
        # Intensity-like small floats (0–20×) without volume scale are not ΔIEV.
        # Locked ΔIEV is share volume (thousands+). Honest — for ambiguous tiny floats.
        if isinstance(raw, float) and abs(raw) < 100 and not float(raw).is_integer():
            # Could be ratio; only accept if clearly volume-scale or int-like shares
            return "—"
        signed = int(raw) if float(raw).is_integer() else raw
        if isinstance(signed, float):
            return _fmt_signed_volume(signed)
        return _fmt_signed_volume(float(signed))
    s = str(raw).strip()
    if not s or s in {"None", "—", "-"}:
        return "—"
    # Reject pure intensity copy patterns like "1.34" without unit
    try:
        f = float(s.replace(",", "").replace("+", ""))
        if abs(f) < 100 and "M" not in s.upper() and "K" not in s.upper():
            return "—"
    except ValueError:
        pass
    return s


def _risk_annotate(candidate: Any, extras: dict[str, Any]) -> str:
    """RiskEngine annotate (↑/↓/~) or notation; never local clear/watch/block theater."""
    # Direct field
    for key in ("risk", "risk_annotate", "risk_symbol"):
        raw = getattr(candidate, key, None)
        if raw is not None and str(raw).strip() not in {"", "None"}:
            return _normalize_risk(str(raw))

    risks = extras.get("risk_by_ticker") or {}
    ticker = str(getattr(candidate, "ticker", "") or "")
    summary = risks.get(ticker) or risks.get(ticker.upper())
    if summary is not None:
        level = getattr(summary, "risk_level_name", None) or getattr(summary, "risk_level", None)
        if level is not None:
            return _risk_from_level(str(level))

    # Notation only (UMA / SUSP) as secondary risk chrome
    notation = getattr(candidate, "ticker_notation", None)
    if notation is not None:
        code = getattr(notation, "code", None) or getattr(notation, "notation", None)
        if code:
            return str(code)[:6]
    return "—"


def _risk_from_level(level: str) -> str:
    u = level.upper()
    if u in {"LOW_RISK", "LOW", "OPEN"}:
        return "↑"
    if u in {"HIGH_RISK", "HIGH", "BLOCK", "BLOCKED"}:
        return "↓"
    if u in {"MEDIUM_RISK", "MEDIUM", "MODERATE", "WATCH"}:
        return "~"
    return "—"


def _normalize_risk(raw: str) -> str:
    s = raw.strip()
    if s in {"↑", "↓", "~", "—", "-"}:
        return "—" if s == "-" else s
    u = s.upper()
    # Legacy theater tokens → honest dash (do not re-paint as authority)
    if u in {"CLEAR", "WATCH", "BLOCK", "BLOCKED", "PASS", "FAIL", "WARN", "OPEN"}:
        mapped = _risk_from_level(u)
        # CLEAR was local theater; only map real RiskEngine levels
        if u in {"CLEAR", "PASS", "OPEN"}:
            return "—"
        if u in {"BLOCK", "BLOCKED", "FAIL"}:
            return "↓"
        if u in {"WATCH", "WARN"}:
            return "~"
        return mapped
    if u in {"LOW_RISK", "HIGH_RISK", "MEDIUM_RISK"}:
        return _risk_from_level(u)
    return s if len(s) <= 8 else "—"


def _fmt_volume(v: float | int) -> str:
    fv = float(v)
    if abs(fv) >= 1_000_000:
        return f"{fv / 1_000_000:.1f}M"
    if abs(fv) >= 1000:
        return f"{fv / 1000:.0f}K"
    return f"{fv:.0f}"


def _fmt_signed_volume(v: float) -> str:
    sign = "+" if v > 0 else ""
    return f"{sign}{_fmt_volume(v)}" if v != 0 else "0"


def _evidence_line(
    candidate: Any,
    *,
    action: str,
    ncp: str,
    delta_iev: str,
    delta: str,
    iev: str,
) -> str:
    """Why-line material for focus / inspect — conf/quality live here, not Grd column."""
    parts: list[str] = []
    trend = getattr(candidate, "trend_signal", None) or ""
    if trend:
        parts.append(f"Dir {trend}")
    tag = getattr(candidate, "opening_broker_backing_tag", None) or ""
    if tag:
        parts.append(f"broker {tag}")
    if action and action != "—":
        parts.append(f"Act {action}")
    parts.append(f"NCP {ncp}")
    if delta_iev and delta_iev != "—":
        parts.append(f"ΔIEV {delta_iev}")
    else:
        parts.append("delta_iev_missing")
    gap_src = getattr(candidate, "gap_price_source", None) or ""
    if gap_src:
        parts.append(f"gap {gap_src}")
    elif delta != "—":
        parts.append(f"gap {delta}")
    intensity = getattr(candidate, "iev_intensity", None)
    if isinstance(intensity, (int, float)):
        parts.append(f"intensity {float(intensity):.1f}×")
    return " · ".join(parts) if parts else f"IEV {iev}"


def _session_strip(
    *,
    rows: tuple[PreOpenRowView, ...],
    candidates: list[Any],
    snapshot_date: str,
    warnings: list[str],
    extras: dict[str, Any],
    payload: Any,
) -> PreOpenSessionStrip:
    # Source
    live = extras.get("source_is_live")
    if live is True:
        source = "LIVE"
    elif not candidates and not snapshot_date:
        source = "EMPTY"
    else:
        source = "SNAPSHOT"

    # Phase — honesty first
    ncp_auth = extras.get("ncp_authoritative")
    phase_raw = str(extras.get("capture_phase") or "").upper()
    if ncp_auth is True or phase_raw == "NCP_LOCKED":
        phase = "NCP_LOCKED"
    elif phase_raw in {"OUTSIDE WINDOW", "OUTSIDE_WINDOW", "INVALID_WINDOW"}:
        phase = "OUTSIDE WINDOW"
        source = "OUTSIDE WINDOW"
    else:
        # Snapshot / discovery path
        reason = "no Action authority" if all(r.action == "—" for r in rows) else "snapshot"
        phase = f"discovery-only ({reason})" if rows else "discovery-only"

    # Funnel — Action counts only when Act is available
    scanned = extras.get("total_movers_seen")
    if scanned is None:
        scanned = len(candidates)
    n_cand = len(rows)
    enter_n = sum(1 for r in rows if r.action.upper() == "ENTER")
    watch_n = sum(1 for r in rows if r.action.upper() == "WATCH")
    has_action = any(r.action != "—" for r in rows)
    if has_action:
        funnel = f"{scanned} · {n_cand} · E{enter_n}/W{watch_n}"
    else:
        funnel = f"{scanned} · {n_cand} · E—/W—"

    # Clock / window
    if snapshot_date:
        window = f"as of {snapshot_date}"
    else:
        window = "window closed · no snapshot"

    return PreOpenSessionStrip(
        source=source,
        phase=phase,
        funnel=funnel,
        window=window,
    )


def format_preopen_why(row: PreOpenRowView | Any) -> str:
    """One-line Why for focus strip, Enter inspect, and plan confirm.

    Prefer ``row.evidence`` so all surfaces stay board-identical (no re-grade).
    """
    evidence = str(getattr(row, "evidence", "") or "").strip()
    if evidence:
        return evidence
    action = str(getattr(row, "action", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    ncp = str(getattr(row, "ncp", "—") or "—")
    return f"Act {action} · risk {risk} · NCP {ncp}"


@dataclass(frozen=True)
class PreOpenFocusView:
    """Focus strip + sidebar for one pre-open row."""

    strip: str
    focus_sidebar: str
    why: str = ""


def build_preopen_focus(
    row: PreOpenRowView | Any,
    *,
    rank: int = 1,
    total: int = 1,
    session_strip: PreOpenSessionStrip | None = None,
) -> PreOpenFocusView:
    """Present-only focus text aligned with board cells."""
    ticker = str(getattr(row, "ticker", "?"))
    why = format_preopen_why(row)
    action = str(getattr(row, "action", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    iep = str(getattr(row, "iep", "—") or "—")
    delta = str(getattr(row, "delta_pct", "—") or "—")
    iev = str(getattr(row, "iev", "—") or "—")
    ncp = str(getattr(row, "ncp", "—") or "—")
    delta_iev = str(getattr(row, "delta_iev", "—") or "—")

    lines: list[str] = []
    if session_strip is not None:
        lines.append(
            f"[#9b8fb8]Session[/]  {session_strip.source} · {session_strip.phase} · "
            f"{session_strip.funnel} · {session_strip.window}"
        )
    lines.append(f"[#9b8fb8]Focus · {ticker}[/]  #{rank}/{total}  ·  Act {action} · risk {risk}")
    lines.append(f"[#d4b06a]Why[/]  {why}" if why else "Why  —")
    lines.append(f"IEP {iep} · Δ% {delta} · IEV {iev} · NCP {ncp} · ΔIEV {delta_iev}")
    strip = "\n".join(lines)
    short_why = why if len(why) <= 42 else why[:39] + "…"
    sidebar = f"{ticker} · Act {action}\n{short_why}"
    return PreOpenFocusView(strip=strip, focus_sidebar=sidebar, why=why)
