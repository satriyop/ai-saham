"""Structured desk top-matrix model (present-only).

Builds from ViewBrokerDeskTopMatrixResult — no re-ranking.
Cell: ticker · desk×ticker streak · net (partial mark) · avg buy.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.trade_action_labels import ACTION_SCAN_TOKENS
from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType

DEFAULT_MATRIX_WINDOWS: tuple[int, ...] = (1, 3, 5, 10, 20)
DEFAULT_MATRIX_LIMIT: int = 5
HUB_KEYS = "t buy/sell · f flow · c calendar · h history · m top 5 · v ticker · esc home"


@dataclass(frozen=True)
class BrokerMatrixCellView:
    """One painted matrix cell (rank × window)."""

    ticker: str
    streak_label: str  # e.g. "6s"
    net_display: str
    avg_buy_display: str  # e.g. "@ 9,850" or "—"
    is_default_window: bool  # emphasize 1s
    is_partial: bool
    empty: bool = False


@dataclass(frozen=True)
class BrokerDeskMatrixModel:
    """Everything the matrix widget needs (no IO)."""

    broker_code: str
    broker_name: str
    type_label: str
    as_of: str
    sessions_cached: int
    scope_note: str
    windows: tuple[int, ...]
    # rows[rank][col_index] aligned to windows
    rows: tuple[tuple[BrokerMatrixCellView, ...], ...]
    default_window: int
    hub_keys: str
    jump_ticker: str | None
    empty: bool = False
    empty_reason: str = ""

    def body_contains_action_authority(self) -> bool:
        blobs = [self.scope_note, self.hub_keys, self.empty_reason, self.broker_name]
        for row in self.rows:
            for cell in row:
                blobs.append(cell.ticker)
        text = " ".join(blobs).upper()
        for token in ACTION_SCAN_TOKENS[:3]:
            if token in f" {text} ":
                return True
        return False


def _type_label(broker_type: Any) -> str:
    if broker_type == BrokerType.FOREIGN:
        return "Foreign"
    if broker_type == BrokerType.LOCAL:
        return "Local"
    if isinstance(broker_type, str):
        return broker_type
    return "—"


def _fmt_avg_buy(avg: Any) -> str:
    if avg is None:
        return "—"
    try:
        d = Decimal(str(avg))
    except Exception:
        return "—"
    if d == d.to_integral_value():
        return f"@ {int(d):,}"
    return f"@ {d:,.2f}"


def _net_display(cell: Any) -> str:
    """Net with optional + and partial *(used/window) mark."""
    nv = getattr(cell, "net_value", None)
    if nv is None:
        return "—"
    d = Decimal(str(nv))
    base = format_value(d)
    if d > 0 and not base.startswith("+"):
        base = f"+{base}"
    used = int(getattr(cell, "sessions_used", 0) or 0)
    win = int(getattr(cell, "window", 0) or 0)
    if 0 < used < win:
        return f"{base}*({used}/{win})"
    return base


def _empty_cell(*, default: bool) -> BrokerMatrixCellView:
    return BrokerMatrixCellView(
        ticker="—",
        streak_label="",
        net_display="—",
        avg_buy_display="—",
        is_default_window=default,
        is_partial=False,
        empty=True,
    )


def build_broker_desk_matrix_model(
    result: Any | None,
    *,
    code: str = "",
    default_window: int = 1,
    empty_reason: str = "",
) -> BrokerDeskMatrixModel:
    """Pure present model from top-matrix use-case result."""
    if result is None:
        code_u = str(code or "—").upper()
        wins = DEFAULT_MATRIX_WINDOWS
        return BrokerDeskMatrixModel(
            broker_code=code_u,
            broker_name=code_u,
            type_label="—",
            as_of="—",
            sessions_cached=0,
            scope_note="Tracked desk activity only",
            windows=wins,
            rows=(),
            default_window=default_window,
            hub_keys=HUB_KEYS,
            jump_ticker=None,
            empty=True,
            empty_reason=empty_reason
            or "no broker_daily_flow for this desk · run broker fetch first",
        )

    code_u = str(getattr(result, "broker_code", code) or code or "—").upper()
    wins = tuple(getattr(result, "windows", None) or DEFAULT_MATRIX_WINDOWS)
    columns = getattr(result, "columns", None) or {}
    limit = max((len(columns.get(w) or ()) for w in wins), default=0)
    limit = min(max(limit, 0), DEFAULT_MATRIX_LIMIT)

    rows_out: list[tuple[BrokerMatrixCellView, ...]] = []
    for rank in range(limit):
        cells: list[BrokerMatrixCellView] = []
        for w in wins:
            col = columns.get(w) or ()
            is_def = w == default_window
            if rank >= len(col):
                cells.append(_empty_cell(default=is_def))
                continue
            c = col[rank]
            streak_n = int(getattr(c, "buy_streak", 0) or 0)
            cells.append(
                BrokerMatrixCellView(
                    ticker=str(getattr(c, "ticker", "—")).upper(),
                    streak_label=f"{streak_n}s",
                    net_display=_net_display(c),
                    avg_buy_display=_fmt_avg_buy(getattr(c, "avg_buy_price", None)),
                    is_default_window=is_def,
                    is_partial=bool(getattr(c, "is_partial", False)),
                    empty=False,
                )
            )
        rows_out.append(tuple(cells))

    jump = getattr(result, "top_ticker_1s", None)
    if callable(jump):
        jump = jump()
    as_of = getattr(result, "as_of", None)
    as_of_s = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of or "—")

    empty = len(rows_out) == 0
    return BrokerDeskMatrixModel(
        broker_code=code_u,
        broker_name=str(getattr(result, "broker_name", code_u) or code_u),
        type_label=_type_label(getattr(result, "broker_type", None)),
        as_of=as_of_s,
        sessions_cached=int(getattr(result, "sessions_cached", 0) or 0),
        scope_note=str(
            getattr(result, "scope_note", None)
            or "Tracked desk activity only · top net buy by window"
        ),
        windows=wins,
        rows=tuple(rows_out),
        default_window=default_window,
        hub_keys=HUB_KEYS,
        jump_ticker=str(jump).upper() if jump else None,
        empty=empty,
        empty_reason="no net-buy names in windows" if empty else "",
    )


def format_broker_desk_matrix_scraper_text(model: BrokerDeskMatrixModel) -> str:
    """Plain-text mirror for scrapers / journey tests reading _detail_text."""
    lines = [
        f"Desk Top Matrix · {model.broker_code} ({model.broker_name})",
        (
            f"type {model.type_label} · as of {model.as_of} · "
            f"sessions cached {model.sessions_cached}"
        ),
        model.scope_note,
        "cell: ticker · streak · net · avg buy · *partial = sessions < window",
        "",
    ]
    header = f"{'#':>2}"
    for w in model.windows:
        header += f"  |  {w}s".ljust(28)
    lines.append(header.rstrip())
    lines.append("-" * min(120, 4 + 28 * len(model.windows)))
    if model.empty or not model.rows:
        lines.append(f"  — {model.empty_reason or 'no net-buy names in windows'}")
    for rank, row in enumerate(model.rows):
        line = f"{rank + 1:>2}"
        for cell in row:
            if cell.empty:
                chunk = "—"
            else:
                chunk = (
                    f"{cell.ticker} {cell.streak_label} {cell.net_display} {cell.avg_buy_display}"
                )
            line += f"  |  {chunk[:26]:26}"
        lines.append(line)
    lines.append("")
    lines.append("Actions (TUI)")
    lines.append(f"  {model.hub_keys}")
    return "\n".join(lines)
