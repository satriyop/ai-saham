"""Present pre-open screen response as dense board rows.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PreOpenRowView:
    ticker: str
    iep: str
    delta_pct: str
    iev: str
    ncp: str
    delta_iev: str
    grade: str
    risk: str
    evidence: str = ""
    source: Any = None


@dataclass(frozen=True)
class PreOpenBoardView:
    rows: tuple[PreOpenRowView, ...]
    meta: str
    cache_label: str


class PreOpenPresenter:
    def present(self, payload: Any) -> PreOpenBoardView:
        candidates, snapshot_date, warnings = _extract(payload)
        rows = tuple(_row(c) for c in candidates)
        meta_bits = [f"{len(rows)} graded"]
        if snapshot_date:
            meta_bits.insert(0, f"IEP snapshot {snapshot_date}")
        if warnings:
            meta_bits.append(f"{len(warnings)} warn")
        cache = f"snapshot · {snapshot_date}" if snapshot_date else "local"
        return PreOpenBoardView(rows=rows, meta=" · ".join(meta_bits), cache_label=cache)


def _extract(payload: Any) -> tuple[list[Any], str, list[str]]:
    if payload is None:
        return [], "", []
    snapshot_date = str(getattr(payload, "snapshot_date", "") or "")
    warnings = list(getattr(payload, "warnings", ()) or [])
    response = getattr(payload, "response", payload)
    result = getattr(response, "result", response)
    candidates = list(getattr(result, "candidates", ()) or [])
    return candidates, snapshot_date, warnings


def _row(candidate: Any) -> PreOpenRowView:
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
        iev = f"{iev_raw / 1_000_000:.1f}M" if iev_raw >= 1_000_000 else f"{iev_raw / 1000:.0f}K"
    else:
        iev = "—"

    intensity = getattr(candidate, "iev_intensity", None)
    ncp = f"{float(intensity):.2f}" if isinstance(intensity, (int, float)) else "—"
    delta_iev = ncp if ncp != "—" else "—"

    tag = getattr(candidate, "opening_broker_backing_tag", None) or ""
    trend = getattr(candidate, "trend_signal", None) or ""
    grade = _grade(tag, trend, gap_f)
    risk = _risk(tag, gap_f)

    evidence = f"trend {trend or '—'} · broker {tag or '—'} · gap {delta} · IEV {iev}"
    return PreOpenRowView(
        ticker=ticker,
        iep=iep,
        delta_pct=delta,
        iev=iev,
        ncp=ncp,
        delta_iev=delta_iev,
        grade=grade,
        risk=risk,
        evidence=evidence,
        source=candidate,
    )


def _grade(tag: str, trend: str, gap: float | None) -> str:
    tag_u = (tag or "").upper()
    trend_u = (trend or "").upper()
    if tag_u == "BACKED" and trend_u in {"BULLISH", "NEUTRAL"}:
        return "A"
    if tag_u == "BACKED":
        return "B"
    if tag_u == "DISTRIBUTING":
        return "C"
    if gap is not None and abs(gap) >= 3:
        return "C"
    if trend_u == "BULLISH":
        return "B"
    return "C"


def _risk(tag: str, gap: float | None) -> str:
    if (tag or "").upper() == "DISTRIBUTING":
        return "block"
    if gap is not None and abs(gap) >= 4:
        return "watch"
    return "clear"


def format_preopen_why(row: PreOpenRowView) -> str:
    """One-line Why for focus strip, Enter inspect, and plan confirm.

    Prefer ``row.evidence`` so all surfaces stay board-identical (no re-grade).
    """
    evidence = str(getattr(row, "evidence", "") or "").strip()
    if evidence:
        return evidence
    grade = str(getattr(row, "grade", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    return f"grade {grade} · risk {risk}"


@dataclass(frozen=True)
class PreOpenFocusView:
    """Focus strip + sidebar for one pre-open row."""

    strip: str
    focus_sidebar: str
    why: str = ""


def build_preopen_focus(
    row: PreOpenRowView,
    *,
    rank: int = 1,
    total: int = 1,
) -> PreOpenFocusView:
    """Present-only focus text aligned with board cells."""
    ticker = str(getattr(row, "ticker", "?"))
    why = format_preopen_why(row)
    grade = str(getattr(row, "grade", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    iep = str(getattr(row, "iep", "—") or "—")
    delta = str(getattr(row, "delta_pct", "—") or "—")
    line1 = f"[#9b8fb8]Focus · {ticker}[/]  #{rank}/{total}  ·  grade {grade} · risk {risk}"
    line2 = f"[#d4b06a]Why[/]  {why}" if why else "Why  —"
    iev = getattr(row, "iev", "—")
    ncp = getattr(row, "ncp", "—")
    line3 = f"IEP {iep} · Δ% {delta} · IEV {iev} · NCP {ncp}"
    strip = "\n".join([line1, line2, line3])
    short_why = why if len(why) <= 42 else why[:39] + "…"
    sidebar = f"{ticker} · grade {grade}\n{short_why}"
    return PreOpenFocusView(strip=strip, focus_sidebar=sidebar, why=why)
