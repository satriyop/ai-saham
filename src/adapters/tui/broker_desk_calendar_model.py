"""Structured desk calendar model (present-only).

Month grid cells (design mock ``desk-cal``): day number · top stock · net · B/S.
Tracked desk only — not market foreign total.

Layer: Adapter
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType

# Full month grid: up to 6 weeks × 7 days
MAX_GRID_CELLS: int = 42
DISPLAY_LIMIT: int = 22  # scraper row cap (session list)
HUB_KEYS = "t buy/sell · f flow · c calendar · h history · m top 5 · v ticker · esc home"
LEGEND = (
    "Ticker = top stock this desk net-bought that day · net = desk day net · empty = no session"
)
DOW_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class BrokerCalendarDayView:
    """Session row (scraper / list export)."""

    date_label: str
    top_ticker: str
    net_display: str
    buy_display: str
    sell_display: str
    ticker_count: str
    tone: str  # pos | neg | flat


@dataclass(frozen=True)
class BrokerCalendarCellView:
    """One month-grid cell (mock ``.day``)."""

    kind: str  # pad | blank | session
    day_num: int | None
    top_ticker: str
    net_display: str
    buy_display: str
    sell_display: str
    tone: str  # pos | neg | flat | ""
    is_as_of: bool = False

    @property
    def is_empty_slot(self) -> bool:
        return self.kind == "pad"


@dataclass(frozen=True)
class BrokerDeskCalendarModel:
    broker_code: str
    broker_name: str
    type_label: str
    as_of: str
    sessions_cached: int
    scope_note: str
    days: tuple[BrokerCalendarDayView, ...]
    cells: tuple[BrokerCalendarCellView, ...]
    month_label: str
    summary: str
    legend: str
    hub_keys: str
    jump_ticker: str | None
    empty: bool = False
    empty_reason: str = ""

    def body_contains_action_authority(self) -> bool:
        text = f"{self.scope_note} {self.hub_keys} {self.empty_reason} {self.legend}".upper()
        for token in (" ENTER ", " WATCH ", " AVOID "):
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


def _signed(value: Decimal) -> tuple[str, str]:
    base = format_value(value)
    if value > 0 and not base.startswith("+"):
        return f"+{base}", "pos"
    if value < 0:
        return base, "neg"
    return base, "flat"


def _parse_date(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    if raw is None:
        return None
    if hasattr(raw, "isoformat") and hasattr(raw, "year"):
        try:
            return date(int(raw.year), int(raw.month), int(raw.day))
        except (TypeError, ValueError):
            return None
    s = str(raw)
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _compact_bs(buy: Decimal, sell: Decimal) -> tuple[str, str]:
    """Short B/S for cell footer (mock ``B 2.1 · S 1.4`` style)."""
    return format_value(buy), format_value(sell)


def build_month_grid_cells(
    session_days: list[Any],
    *,
    as_of: date,
) -> tuple[tuple[BrokerCalendarCellView, ...], str, str, int]:
    """Build Mon-start month grid for ``as_of``'s calendar month.

    Returns (cells, month_label, summary, session_count_in_month).
    """
    year, month = as_of.year, as_of.month
    month_label = as_of.strftime("%b %Y")

    by_day: dict[int, Any] = {}
    for d in session_days:
        dt = _parse_date(getattr(d, "date", None))
        if dt is None or dt.year != year or dt.month != month:
            continue
        # keep first seen; callers usually pass unique dates
        by_day.setdefault(dt.day, d)

    first_wd = date(year, month, 1).weekday()  # Mon=0
    n_days = calendar.monthrange(year, month)[1]

    cells: list[BrokerCalendarCellView] = []
    for _ in range(first_wd):
        cells.append(
            BrokerCalendarCellView(
                kind="pad",
                day_num=None,
                top_ticker="",
                net_display="",
                buy_display="",
                sell_display="",
                tone="",
            )
        )

    buy_sum = Decimal("0")
    sell_sum = Decimal("0")
    sessions = 0
    for day_n in range(1, n_days + 1):
        raw = by_day.get(day_n)
        if raw is None:
            cells.append(
                BrokerCalendarCellView(
                    kind="blank",
                    day_num=day_n,
                    top_ticker="",
                    net_display="",
                    buy_display="",
                    sell_display="",
                    tone="",
                    is_as_of=(day_n == as_of.day),
                )
            )
            continue
        sessions += 1
        nv = Decimal(str(getattr(raw, "net_value", 0) or 0))
        bv = Decimal(str(getattr(raw, "buy_value", 0) or 0))
        sv = Decimal(str(getattr(raw, "sell_value", 0) or 0))
        buy_sum += bv
        sell_sum += sv
        net_s, tone = _signed(nv)
        buy_s, sell_s = _compact_bs(bv, sv)
        top = str(getattr(raw, "top_ticker", None) or "—").upper()
        cells.append(
            BrokerCalendarCellView(
                kind="session",
                day_num=day_n,
                top_ticker=top,
                net_display=net_s,
                buy_display=buy_s,
                sell_display=sell_s,
                tone=tone,
                is_as_of=(day_n == as_of.day),
            )
        )

    while len(cells) % 7:
        cells.append(
            BrokerCalendarCellView(
                kind="pad",
                day_num=None,
                top_ticker="",
                net_display="",
                buy_display="",
                sell_display="",
                tone="",
            )
        )

    # Cap to 6 weeks if something weird
    cells = cells[:MAX_GRID_CELLS]
    while len(cells) < MAX_GRID_CELLS:
        cells.append(
            BrokerCalendarCellView(
                kind="pad",
                day_num=None,
                top_ticker="",
                net_display="",
                buy_display="",
                sell_display="",
                tone="",
            )
        )

    summary = (
        f"{sessions} sessions · buy {format_value(buy_sum)} · "
        f"sell {format_value(sell_sum)} · desk only"
    )
    return tuple(cells), month_label, summary, sessions


def build_broker_desk_calendar_model(
    result: Any | None,
    *,
    code: str = "",
    empty_reason: str = "",
) -> BrokerDeskCalendarModel:
    if result is None:
        code_u = str(code or "—").upper()
        empty_cells = tuple(
            BrokerCalendarCellView(
                kind="pad",
                day_num=None,
                top_ticker="",
                net_display="",
                buy_display="",
                sell_display="",
                tone="",
            )
            for _ in range(MAX_GRID_CELLS)
        )
        return BrokerDeskCalendarModel(
            broker_code=code_u,
            broker_name=code_u,
            type_label="—",
            as_of="—",
            sessions_cached=0,
            scope_note="Tracked desk activity only · not market foreign total",
            days=(),
            cells=empty_cells,
            month_label="—",
            summary="0 sessions · desk only",
            legend=LEGEND,
            hub_keys=HUB_KEYS,
            jump_ticker=None,
            empty=True,
            empty_reason=empty_reason
            or "no broker_daily_flow for this desk · run broker fetch first",
        )

    code_u = str(getattr(result, "broker_code", code) or code or "—").upper()
    raw = list(getattr(result, "days", ()) or ())
    as_of_raw = getattr(result, "as_of", None)
    as_of_d = _parse_date(as_of_raw) or date.today()
    as_of_s = as_of_d.isoformat()

    # Session list newest-first for scraper
    raw_rev = list(reversed(raw))
    views: list[BrokerCalendarDayView] = []
    for d in raw_rev[:DISPLAY_LIMIT]:
        nv = Decimal(str(getattr(d, "net_value", 0) or 0))
        net_s, tone = _signed(nv)
        bv = Decimal(str(getattr(d, "buy_value", 0) or 0))
        sv = Decimal(str(getattr(d, "sell_value", 0) or 0))
        dt = _parse_date(getattr(d, "date", None))
        date_s = dt.isoformat() if dt else str(getattr(d, "date", None) or "—")
        top = getattr(d, "top_ticker", None) or "—"
        views.append(
            BrokerCalendarDayView(
                date_label=date_s,
                top_ticker=str(top).upper(),
                net_display=net_s,
                buy_display=format_value(bv),
                sell_display=format_value(sv),
                ticker_count=str(int(getattr(d, "ticker_count", 0) or 0)),
                tone=tone,
            )
        )

    cells, month_label, summary, _sess_in_month = build_month_grid_cells(raw, as_of=as_of_d)

    jump = None
    for v in views:
        if v.top_ticker and v.top_ticker != "—":
            jump = v.top_ticker
            break
    empty = not views
    return BrokerDeskCalendarModel(
        broker_code=code_u,
        broker_name=str(getattr(result, "broker_name", code_u) or code_u),
        type_label=_type_label(getattr(result, "broker_type", None)),
        as_of=as_of_s,
        sessions_cached=int(getattr(result, "sessions_cached", 0) or 0),
        scope_note=str(
            getattr(result, "scope_note", None)
            or "Tracked desk activity only · not market foreign total"
        ),
        days=tuple(views),
        cells=cells,
        month_label=month_label,
        summary=summary,
        legend=LEGEND,
        hub_keys=HUB_KEYS,
        jump_ticker=jump,
        empty=empty,
        empty_reason="no session days in window" if empty else "",
    )


def format_broker_desk_calendar_scraper_text(model: BrokerDeskCalendarModel) -> str:
    """Text export for loaders/tests — includes month summary + session rows."""
    lines = [
        f"Desk Calendar · {model.broker_code} ({model.broker_name})",
        f"type {model.type_label} · as of {model.as_of} · sessions {model.sessions_cached}",
        f"Month · {model.month_label} · {model.summary}",
        model.scope_note,
        model.legend,
        "",
        f"{'Date':12}  {'Top':6}  {'Net':>10}  {'Buy':>10}  {'Sell':>10}  #",
        "-" * 58,
    ]
    if model.days:
        for d in model.days:
            lines.append(
                f"{d.date_label:12}  {d.top_ticker:6}  {d.net_display:>10}  "
                f"{d.buy_display:>10}  {d.sell_display:>10}  {d.ticker_count}"
            )
    else:
        lines.append("  —")
    lines.append("")
    lines.append("Actions (TUI)")
    lines.append(f"  {model.hub_keys}")
    return "\n".join(lines)


def format_calendar_cell_markup(cell: BrokerCalendarCellView) -> str:
    """Rich markup for one day cell (mock hierarchy)."""
    if cell.kind == "pad":
        return ""
    if cell.kind == "blank":
        dn = cell.day_num if cell.day_num is not None else ""
        return f"[#555555]{dn}[/]"
    # session
    dn = cell.day_num if cell.day_num is not None else ""
    tone = cell.tone
    net_col = "#6fbf8a" if tone == "pos" else ("#c97a72" if tone == "neg" else "#a0a0a0")
    stk_col = "#ececec" if tone == "pos" else "#8a8a8a"
    as_mark = " ·" if cell.is_as_of else ""
    lines = [
        f"[#6b6b6b]{dn}{as_mark}[/]",
        f"[bold {stk_col}]{cell.top_ticker or '—'}[/]",
        f"[bold {net_col}]{cell.net_display}[/]",
        f"[#555555]B {cell.buy_display} · S {cell.sell_display}[/]",
    ]
    return "\n".join(lines)
