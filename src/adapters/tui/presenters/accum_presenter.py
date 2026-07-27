"""Present accumulation workflow result as board rows.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AccumRowView:
    ticker: str
    score: str
    rsi: str
    vol: str
    setup: str
    status: str
    name: str = ""
    source: Any = None


@dataclass(frozen=True)
class AccumBoardView:
    rows: tuple[AccumRowView, ...]
    meta: str
    cache_label: str


class AccumPresenter:
    def present(self, payload: Any) -> AccumBoardView:
        projection = _unwrap_single_projection(payload)
        candidates = list(getattr(projection, "candidates", ()) or ())
        rows = tuple(_row(c) for c in candidates)
        window = getattr(projection, "window_days", None) or 7
        as_of = ""
        data_as_of = getattr(projection, "data_as_of", None) or {}
        if isinstance(data_as_of, dict):
            as_of = data_as_of.get("latest_candle_date") or data_as_of.get("as_of") or ""
        meta_bits = [f"window {window}d", f"{len(rows)} names"]
        if as_of:
            meta_bits.insert(0, f"as of {as_of}")
        cache = f"fresh · {as_of}" if as_of else "local"
        return AccumBoardView(rows=rows, meta=" · ".join(meta_bits), cache_label=cache)


def _unwrap_single_projection(payload: Any) -> Any:
    if payload is None:
        return payload
    single = getattr(payload, "single_projection", None)
    if single is not None:
        return single
    # Already a projection or duck-typed container
    if hasattr(payload, "candidates"):
        return payload
    return payload


def _row(candidate: Any) -> AccumRowView:
    ticker = str(getattr(candidate, "ticker", "?"))
    accum = getattr(candidate, "accum_score", None)
    score = f"{float(accum):.0f}" if isinstance(accum, (int, float)) else "—"

    rsi_val = getattr(candidate, "rsi", None)
    if rsi_val is None:
        rsi_val = getattr(candidate, "rsi_14", None)
    rsi = f"{float(rsi_val):.1f}" if isinstance(rsi_val, (int, float)) else "—"

    vol_raw = getattr(candidate, "volume_ratio", None)
    if vol_raw is None:
        vol_raw = getattr(candidate, "rel_volume", None)
    vol = f"{float(vol_raw):.2f}×" if isinstance(vol_raw, (int, float)) else "—"

    setup = "swing"
    phase = getattr(candidate, "setup_phase", None)
    if phase is not None:
        cp = getattr(phase, "current_phase", phase)
        setup = str(getattr(cp, "value", cp))

    status = "pass"
    trade_setup = getattr(candidate, "trade_setup", None)
    if trade_setup is not None:
        action = getattr(trade_setup, "action", None)
        status = str(getattr(action, "value", action) or status).lower()
    risk = getattr(candidate, "risk_assessment", None)
    if risk is not None:
        level = getattr(risk, "risk_level_name", None) or getattr(risk, "risk_level", None)
        if level and str(level).upper() in {"HIGH", "BLOCK", "BLOCKED"}:
            status = "block"
        elif status == "pass" and level and "watch" in str(level).lower():
            status = "watch"

    name = str(getattr(candidate, "name", "") or getattr(candidate, "company_name", "") or "")
    return AccumRowView(
        ticker=ticker,
        score=score,
        rsi=rsi,
        vol=vol,
        setup=setup,
        status=status,
        name=name,
        source=candidate,
    )
