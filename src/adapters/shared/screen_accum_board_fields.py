"""Single field extraction for screen-accum board rows (CLI + TUI).

Maps an ``AccumulationCandidate`` (or duck-typed equivalent) to plain display
strings and raw scalars. No scoring, no IO, no framework.

Both adapters must read board numbers through this module so Signal/Accum/Action
/Gate cannot be remapped differently per surface.

Layer: Adapter (shared display)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from src.adapters.shared.score_display_labels import ACCUM, SIGNAL

PhaseStyle = Literal["short", "full"]

# Dense TUI / compact boards
_PHASE_SHORT = {
    "NONE": "NONE",
    "ACCUMULATION": "ACCUM",
    "COMPRESSION": "COMPRESS",
    "BREAKOUT_CONFIRMATION": "BREAKOUT",
    "EXHAUSTION": "EXHAUST",
    "DISTRIBUTION": "DISTRIB",
    "FAILED": "FAILED",
}

# CLI action table phase labels (screen_accum_formatters._PHASE_LABELS)
_PHASE_FULL = {
    "NONE": "NONE",
    "ACCUMULATION": "ACCUMULATION",
    "COMPRESSION": "COMPRESSION",
    "BREAKOUT_CONFIRMATION": "BREAKOUT",
    "EXHAUSTION": "EXHAUSTION",
    "DISTRIBUTION": "DISTRIBUTION",
    "FAILED": "FAILED",
}

BOARD_COLUMN_LABELS: tuple[str, ...] = (
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


@dataclass(frozen=True)
class ScreenAccumBoardFields:
    """Plain board fields for one candidate (option-B desk + CLI core cells)."""

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
    # Raw scalars for parity tests (no formatting)
    signal_score: int | None = None
    accum_score: float | None = None
    action_value: str | None = None
    net_buy_ratio: float | None = None
    vwap_discount_pct: float | None = None
    consecutive_streak: int | None = None
    rsi_value: float | None = None
    price_value: float | None = None
    gate_blocked: bool | None = None


def extract_screen_accum_board_fields(
    candidate: Any,
    *,
    phase_style: PhaseStyle = "short",
) -> ScreenAccumBoardFields:
    """Extract board fields from one screen-accum candidate."""
    ticker = str(getattr(candidate, "ticker", "?") or "?")

    signal_score = _raw_signal_score(candidate)
    signal = f"{signal_score}" if signal_score is not None else "—"

    accum_score = _raw_accum_score(candidate)
    accum = f"{accum_score:.1f}" if accum_score is not None else "—"

    action_value, action = _action(candidate)
    phase = _phase(candidate, phase_style=phase_style)

    streak_i = _raw_streak(candidate)
    streak = str(streak_i) if streak_i is not None else "—"

    rsi_v = _raw_rsi(candidate)
    rsi = f"{rsi_v:.1f}" if rsi_v is not None else "—"

    net_r = _raw_net_ratio(candidate)
    net_pct = f"{net_r * 100:.0f}%" if net_r is not None else "—"

    disc_v = _raw_disc(candidate)
    disc_pct = f"{disc_v:+.1f}%" if disc_v is not None else "—"

    price_v = _raw_price(candidate)
    if price_v is not None:
        try:
            price = f"{int(price_v):,}"
        except (TypeError, ValueError):
            price = str(price_v)
    else:
        price = "—"

    gate_blocked = _raw_gate_blocked(candidate)
    if gate_blocked is None:
        gate = "—"
    elif gate_blocked:
        gate = "BLOCKED"
    else:
        gate = "OPEN"

    return ScreenAccumBoardFields(
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
        signal_score=signal_score,
        accum_score=accum_score,
        action_value=action_value,
        net_buy_ratio=net_r,
        vwap_discount_pct=disc_v,
        consecutive_streak=streak_i,
        rsi_value=rsi_v,
        price_value=price_v,
        gate_blocked=gate_blocked,
    )


def _raw_signal_score(candidate: Any) -> int | None:
    sa = getattr(candidate, "signal_assessment", None)
    if sa is None:
        return None
    assessment = getattr(sa, "assessment", None)
    if assessment is not None:
        raw = getattr(assessment, "score", None)
    else:
        raw = getattr(sa, "score", None)
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def _raw_accum_score(candidate: Any) -> float | None:
    accum = getattr(candidate, "accum_score", None)
    if isinstance(accum, (int, float)):
        return float(accum)
    return None


def _action(candidate: Any) -> tuple[str | None, str]:
    trade_setup = getattr(candidate, "trade_setup", None)
    if trade_setup is None:
        return None, "—"
    action = getattr(trade_setup, "action", None)
    if action is None:
        return None, "—"
    value = str(getattr(action, "value", action))
    short = getattr(action, "short", None)
    label = str(short) if short else value
    return value, label


def _phase(candidate: Any, *, phase_style: PhaseStyle) -> str:
    phase = getattr(candidate, "setup_phase", None)
    if phase is None:
        return "—"
    current = getattr(phase, "current_phase", None)
    if current is None:
        return "—"
    raw = str(getattr(current, "value", current))
    table = _PHASE_SHORT if phase_style == "short" else _PHASE_FULL
    return table.get(raw, raw)


def _raw_streak(candidate: Any) -> int | None:
    streak = getattr(candidate, "consecutive_streak", None)
    if isinstance(streak, int):
        return streak
    if isinstance(streak, float):
        return int(streak)
    return None


def _raw_rsi(candidate: Any) -> float | None:
    rsi_val = getattr(candidate, "rsi", None)
    if rsi_val is None:
        rsi_val = getattr(candidate, "rsi_14", None)
    if isinstance(rsi_val, Decimal):
        return float(rsi_val)
    if isinstance(rsi_val, (int, float)):
        return float(rsi_val)
    return None


def _raw_net_ratio(candidate: Any) -> float | None:
    ratio = getattr(candidate, "net_buy_ratio", None)
    if isinstance(ratio, (int, float)):
        return float(ratio)
    return None


def _raw_disc(candidate: Any) -> float | None:
    disc = getattr(candidate, "vwap_discount_pct", None)
    if isinstance(disc, Decimal):
        return float(disc)
    if isinstance(disc, (int, float)):
        return float(disc)
    return None


def _raw_price(candidate: Any) -> float | None:
    price = getattr(candidate, "current_price", None)
    if price is None:
        return None
    try:
        return float(price)
    except (TypeError, ValueError):
        return None


def _raw_gate_blocked(candidate: Any) -> bool | None:
    risk = getattr(candidate, "risk_assessment", None)
    if risk is None:
        return None
    triggered = getattr(risk, "gate_triggered", None)
    return bool(triggered)
