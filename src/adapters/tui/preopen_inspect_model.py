"""Pre-open inspect model — Judge-shaped brief (present-only).

Hero Act·Risk · Why always · AUCTION always · warn only when non-empty ·
optional [d] detail. No option-chip wall (why/auction+/plan/warn).

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.shared.trade_action_labels import ACTION_SCAN_TOKENS
from src.adapters.tui.presenters.preopen_presenter import format_preopen_why

# Density dual only — optional when there is extra depth (design § Pre-open inspect).
FLAG_DEFS: tuple[tuple[str, str], ...] = (("detail", "detail · d"),)
EXPANDABLE_FLAGS: frozenset[str] = frozenset()  # no option-chip wall


@dataclass(frozen=True)
class PreOpenFlagChip:
    key: str
    label: str
    available: bool
    warn: bool = False


@dataclass(frozen=True)
class PreOpenInspectModel:
    ticker: str
    rank: int
    total: int
    board_meta: str
    action: str
    risk: str
    why: str
    iep: str
    delta_pct: str
    iev: str
    ncp: str
    delta_iev: str
    auction_lines: tuple[str, ...]
    data_lines: tuple[str, ...]
    detail_lines: tuple[str, ...]
    warn_lines: tuple[str, ...]
    flags: tuple[PreOpenFlagChip, ...]
    footer: str
    has_auction_depth: bool
    has_warn: bool
    has_detail: bool
    present_only: bool = True

    def body_contains_action_authority(self) -> bool:
        """Browse/inspect body must not invent Action labels as authority theater.

        Hero ``action`` is display of board Act (may be — on discovery). Why/footer
        should not inject ENTER/WATCH as if they were computed here.
        """
        # Strip the legitimate hero action token from the scan surface
        text = f"{self.why} {self.footer} {' '.join(self.auction_lines)}"
        if self.action and self.action != "—":
            text = text.replace(self.action, " ")
        padded = f" {text.upper()} "
        for token in ACTION_SCAN_TOKENS[:3]:
            if token in padded:
                return True
        return False


def build_preopen_inspect_model(
    row: Any,
    *,
    rank: int = 1,
    total: int = 1,
    snapshot_date: str = "",
    board_meta: str = "",
    warnings: tuple[str, ...] = (),
) -> PreOpenInspectModel:
    ticker = str(getattr(row, "ticker", "?") or "?")
    action = str(getattr(row, "action", "—") or "—")
    # Legacy grade field must not become Act theater
    if action in {"A", "B", "C"} and not getattr(row, "action", None):
        action = "—"
    risk = str(getattr(row, "risk", "—") or "—")
    why = format_preopen_why(row) or "—"

    auction_lines, has_auction_depth = _auction(row)
    warn_lines = _warn_lines(row, warnings)
    has_warn = bool(warn_lines)

    snap = (snapshot_date or "").strip() or "—"
    gap_src = ""
    source = getattr(row, "source", None)
    if source is not None:
        gap_src = str(getattr(source, "gap_price_source", None) or "")
    data_lines = (
        f"as of {snap}",
        "source local IEP · IEV · NCP",
        f"gap source {gap_src or '—'}",
    )
    detail_lines = _detail_lines(row, source=source)
    has_detail = bool(detail_lines)

    flags: tuple[PreOpenFlagChip, ...] = ()
    if has_detail:
        flags = (PreOpenFlagChip("detail", "detail · d", available=True),)

    return PreOpenInspectModel(
        ticker=ticker,
        rank=rank,
        total=max(total, 1),
        board_meta=board_meta or "",
        action=action,
        risk=risk,
        why=why,
        iep=str(getattr(row, "iep", "—") or "—"),
        delta_pct=str(getattr(row, "delta_pct", "—") or "—"),
        iev=str(getattr(row, "iev", "—") or "—"),
        ncp=str(getattr(row, "ncp", "—") or "—"),
        delta_iev=str(getattr(row, "delta_iev", "—") or "—"),
        auction_lines=auction_lines,
        data_lines=data_lines,
        detail_lines=detail_lines,
        warn_lines=warn_lines,
        flags=flags,
        footer="esc board · d detail · p plan · v ticker · Ctrl+P",
        has_auction_depth=has_auction_depth,
        has_warn=has_warn,
        has_detail=has_detail,
    )


def _warn_lines(row: Any, warnings: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for w in list(warnings or ())[:4]:
        out.append(str(w))
    source = getattr(row, "source", None)
    if source is not None:
        notation = getattr(source, "ticker_notation", None)
        if notation is not None:
            code = getattr(notation, "code", None) or getattr(notation, "notation", None)
            if code:
                out.append(str(code))
    return tuple(out[:4])


def _auction(row: Any) -> tuple[tuple[str, ...], bool]:
    """Always-on AUCTION second row; honest — when no book / fast path."""
    source = getattr(row, "source", None)
    if source is None:
        return ("—",), False

    bits: list[str] = []
    imb = getattr(source, "bid_offer_imbalance", None)
    if isinstance(imb, (int, float)):
        bits.append(f"imb {float(imb):.2f}×")
    spread = getattr(source, "spread_pct", None)
    if spread is not None:
        try:
            bits.append(f"spread {float(spread):.2f}%")
        except (TypeError, ValueError):
            pass
    intensity = getattr(source, "iev_intensity", None)
    if isinstance(intensity, (int, float)):
        bits.append(f"intensity {float(intensity):.1f}×")

    tag = getattr(source, "opening_broker_backing_tag", None) or ""
    score = getattr(source, "opening_broker_backing_score", None)
    streak = getattr(source, "opening_broker_buy_streak", None)
    broker_bits: list[str] = []
    if tag:
        broker_bits.append(str(tag))
    if score is not None:
        broker_bits.append(f"backing {score}")
    if streak is not None:
        broker_bits.append(f"streak {streak}")

    lines: list[str] = []
    if bits:
        lines.append(" · ".join(bits))
    if broker_bits:
        lines.append(" · ".join(broker_bits))
    trend = getattr(source, "trend_signal", None)
    if trend:
        lines.append(f"trend {trend}")

    has_depth = bool(bits or broker_bits)
    if not lines:
        return ("—",), False
    return tuple(lines), has_depth


def _detail_lines(row: Any, *, source: Any) -> tuple[str, ...]:
    """Optional depth for [d] detail — factors · full book · rejects."""
    if source is None:
        return ()
    lines: list[str] = []
    for key, label in (
        ("best_bid", "best bid"),
        ("best_offer", "best offer"),
        ("best_bid_lots", "bid lots"),
        ("best_offer_lots", "offer lots"),
        ("rsi", "RSI"),
        ("atr", "ATR"),
        ("prev_close", "prev close"),
        ("foreign_vwap", "FVWAP"),
        ("fvwap_discount_pct", "FVWAP disc%"),
        ("entry_price", "entry"),
        ("stop_loss_price", "stop"),
    ):
        val = getattr(source, key, None)
        if val is not None and str(val) not in {"", "None"}:
            lines.append(f"{label} {val}")
    return tuple(lines)
