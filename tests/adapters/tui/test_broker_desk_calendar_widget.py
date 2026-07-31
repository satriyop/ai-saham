"""Broker calendar month-grid paint hierarchy — pure model (no full-app mount).

Hub ``c`` residual journey: ``test_view_broker_journey`` (or D3 broker list path).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_calendar_model import (
    DOW_LABELS,
    MAX_GRID_CELLS,
    build_broker_desk_calendar_model,
    build_month_grid_cells,
    format_broker_desk_calendar_scraper_text,
    format_calendar_cell_markup,
)
from src.adapters.tui.widgets.broker_calendar_desk import BrokerCalendarDesk
from src.domain.entities.broker_flow import BrokerType


def _day(
    d: date,
    *,
    top: str,
    net: str,
    buy: str | None = None,
    sell: str | None = None,
) -> SimpleNamespace:
    nv = Decimal(net)
    bv = Decimal(buy) if buy is not None else (nv if nv > 0 else Decimal("0"))
    sv = Decimal(sell) if sell is not None else (-nv if nv < 0 else Decimal("0"))
    return SimpleNamespace(
        date=d,
        net_value=nv,
        buy_value=bv,
        sell_value=sv,
        top_ticker=top,
        top_net=nv,
        ticker_count=2,
    )


def _result(*days: SimpleNamespace, as_of: date = date(2026, 7, 29)) -> SimpleNamespace:
    return SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        as_of=as_of,
        sessions_cached=len(days),
        scope_note="Tracked desk activity only · not market foreign total",
        days=days,
    )


def test_month_grid_mon_start_pad_for_july_2026():
    """Jul 2026 starts Wednesday → pad 2 (Mon, Tue)."""
    sessions = [
        _day(date(2026, 7, 1), top="BBRI", net="2100000000"),
        _day(
            date(2026, 7, 29),
            top="AMMN",
            net="11500000000",
            buy="14200000000",
            sell="2700000000",
        ),
    ]
    cells, month_label, summary, n = build_month_grid_cells(sessions, as_of=date(2026, 7, 29))
    assert month_label == "Jul 2026"
    assert n == 2
    assert cells[0].kind == "pad"
    assert cells[1].kind == "pad"
    # day 1 at index 2
    assert cells[2].kind == "session"
    assert cells[2].day_num == 1
    assert cells[2].top_ticker == "BBRI"
    # day 29 at index 2 + 28 = 30
    c29 = cells[2 + 28]
    assert c29.kind == "session"
    assert c29.day_num == 29
    assert c29.top_ticker == "AMMN"
    assert c29.is_as_of is True
    assert c29.tone == "pos"
    assert "AMMN" in format_calendar_cell_markup(c29)
    assert "sessions" in summary.lower()
    assert "desk only" in summary.lower()
    assert len(cells) == MAX_GRID_CELLS


def test_calendar_model_exposes_grid_hierarchy_not_just_rows():
    model = build_broker_desk_calendar_model(
        _result(
            _day(date(2026, 7, 14), top="AMMN", net="4000000000"),
            _day(date(2026, 7, 29), top="BUMI", net="-4400000000"),
        )
    )
    assert model.empty is False
    assert model.month_label == "Jul 2026"
    assert model.legend
    assert "top stock" in model.legend.lower()
    assert len(model.cells) == MAX_GRID_CELLS
    sessions = [c for c in model.cells if c.kind == "session"]
    assert len(sessions) == 2
    tickers = {c.top_ticker for c in sessions}
    assert "AMMN" in tickers and "BUMI" in tickers
    assert model.body_contains_action_authority() is False
    # scraper still has row list for loaders
    text = format_broker_desk_calendar_scraper_text(model)
    assert "Month · Jul 2026" in text
    assert "AMMN" in text


def test_calendar_paint_contract_month_grid_hierarchy():
    """Paint maps model → title/summary/cells/legend/hub (no DOM mount)."""
    model = build_broker_desk_calendar_model(
        _result(
            _day(date(2026, 7, 1), top="BBRI", net="1000000000"),
            _day(date(2026, 7, 29), top="AMMN", net="11500000000"),
        )
    )
    title = f"Calendar · {model.broker_code} · {model.month_label}"
    assert "Calendar · YP · Jul 2026" in title

    summary = f"{model.summary} · {model.scope_note}"
    assert "sessions" in summary.lower()
    assert "desk only" in summary.lower() or "not market foreign" in summary.lower()

    # DOW labels remain Mon–Sun contract for the header row
    assert DOW_LABELS == ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    # Grid is primary (cells), not a row-dump head
    assert len(model.cells) == MAX_GRID_CELLS
    # Jul 2026: pad 2 + day 29 → index 30
    cell29 = model.cells[30]
    markup29 = format_calendar_cell_markup(cell29)
    assert "AMMN" in markup29
    assert "29" in markup29 or cell29.day_num == 29
    classes29 = BrokerCalendarDesk._cell_classes(cell29)
    assert "session" in classes29
    assert "asof" in classes29

    cell1 = model.cells[2]
    assert "BBRI" in format_calendar_cell_markup(cell1)

    assert "top stock" in model.legend.lower() or "net" in model.legend.lower()
    assert "c calendar" in model.hub_keys.lower() or "m top" in model.hub_keys.lower()
    assert "ENTER" not in model.hub_keys.upper().replace("CENTER", "")


def test_calendar_hub_c_model_is_grid_not_row_dump():
    """Structured calendar model for hub c — grid cells, not Date/Top/Net dump."""
    model = build_broker_desk_calendar_model(
        _result(_day(date(2026, 7, 29), top="AMMN", net="1000000000"))
    )
    assert model.month_label == "Jul 2026"
    assert "AMMN" in format_calendar_cell_markup(model.cells[30])
    # No primary row-list shape: cells fill the month grid
    assert len(model.cells) == MAX_GRID_CELLS
    sessions = [c for c in model.cells if c.kind == "session"]
    assert len(sessions) == 1
    assert sessions[0].top_ticker == "AMMN"
