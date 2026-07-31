"""Pre-open inspect model — mock hierarchy (hero · flags · panels).

Present-only from board row. Never invents Signal/Accum/Action.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.shared.trade_action_labels import ACTION_SCAN_TOKENS
from src.adapters.tui.presenters.preopen_presenter import format_preopen_why

FLAG_DEFS: tuple[tuple[str, str], ...] = (
    ("detail", "detail · d"),
    ("why", "why"),
    ("auction_plus", "auction+"),
    ("warn", "warn"),
)
EXPANDABLE_FLAGS = frozenset({"why", "auction_plus", "warn"})


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
    grade: str
    risk: str
    why: str
    iep: str
    delta_pct: str
    iev: str
    ncp: str
    delta_iev: str
    auction_lines: tuple[str, ...]
    data_lines: tuple[str, ...]
    warn_lines: tuple[str, ...]
    flags: tuple[PreOpenFlagChip, ...]
    footer: str
    has_auction: bool
    has_warn: bool

    def body_contains_action_authority(self) -> bool:
        text = f"{self.why} {self.footer}".upper()
        for token in ACTION_SCAN_TOKENS[:3]:
            if token in f" {text} ":
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
    grade = str(getattr(row, "grade", "—") or "—")
    risk = str(getattr(row, "risk", "—") or "—")
    why = format_preopen_why(row) or "—"

    auction_lines, has_auction = _auction(row)
    warn_lines = tuple(f"warning: {w}" for w in list(warnings or ())[:4])
    has_warn = bool(warn_lines)

    snap = (snapshot_date or "").strip() or "—"
    data_lines = (
        f"as of {snap}",
        "source local IEP · IEV · NCP",
    )

    flags = (
        PreOpenFlagChip("detail", "detail · d", available=True),
        PreOpenFlagChip("why", "why", available=bool(why and why != "—")),
        PreOpenFlagChip("auction_plus", "auction+", available=has_auction),
        PreOpenFlagChip("warn", "warn", available=has_warn, warn=True),
    )

    return PreOpenInspectModel(
        ticker=ticker,
        rank=rank,
        total=max(total, 1),
        board_meta=board_meta or "",
        grade=grade,
        risk=risk,
        why=why,
        iep=str(getattr(row, "iep", "—") or "—"),
        delta_pct=str(getattr(row, "delta_pct", "—") or "—"),
        iev=str(getattr(row, "iev", "—") or "—"),
        ncp=str(getattr(row, "ncp", "—") or "—"),
        delta_iev=str(getattr(row, "delta_iev", "—") or "—"),
        auction_lines=auction_lines,
        data_lines=data_lines,
        warn_lines=warn_lines,
        flags=flags,
        footer="d detail · esc board · p plan · Ctrl+P",
        has_auction=has_auction,
        has_warn=has_warn,
    )


def _auction(row: Any) -> tuple[tuple[str, ...], bool]:
    source = getattr(row, "source", None)
    if source is None:
        return ("not on this row",), False
    trend = getattr(source, "trend_signal", None) or "—"
    tag = getattr(source, "opening_broker_backing_tag", None) or "—"
    score = getattr(source, "opening_broker_backing_score", None)
    streak = getattr(source, "opening_broker_buy_streak", None)
    lines = [f"trend {trend} · broker {tag}"]
    extra: list[str] = []
    if score is not None:
        extra.append(f"backing_score {score}")
    if streak is not None:
        extra.append(f"buy_streak {streak}")
    if extra:
        lines.append(" · ".join(extra))
    has = bool(trend != "—" or tag != "—" or score is not None or streak is not None)
    return tuple(lines), has
