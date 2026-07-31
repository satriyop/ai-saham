"""Broker desk matrix pure model — Stage 2 cockpit redesign."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_matrix_model import (
    build_broker_desk_matrix_model,
    format_broker_desk_matrix_scraper_text,
)
from src.application.services.broker_desk_from_daily_flow import DeskTickerWindowCell
from src.domain.entities.broker_flow import BrokerType


def _cell(
    ticker: str,
    net: str,
    *,
    window: int = 1,
    sessions: int = 1,
    avg: str | None = "9850",
    streak: int = 3,
    partial: bool = False,
) -> DeskTickerWindowCell:
    return DeskTickerWindowCell(
        ticker=ticker,
        net_value=Decimal(net),
        window=window,
        sessions_used=sessions,
        avg_buy_price=Decimal(avg) if avg is not None else None,
        buy_streak=streak,
        is_partial=partial,
    )


def _result(**overrides):
    cols = {
        1: (
            _cell("AMMN", "6760000000", window=1, sessions=1, avg="9850", streak=6),
            _cell("BUMI", "5540000000", window=1, sessions=1, avg="148", streak=4),
        ),
        3: (
            _cell(
                "AMMN",
                "18200000000",
                window=3,
                sessions=3,
                avg="9720",
                streak=6,
            ),
        ),
        5: (),
        10: (),
        20: (
            _cell(
                "AMMN",
                "41000000000",
                window=20,
                sessions=7,
                avg="9380",
                streak=6,
                partial=True,
            ),
        ),
    }
    base = dict(
        broker_code="YP",
        broker_name="YP Desk",
        as_of=date(2026, 7, 29),
        broker_type=BrokerType.FOREIGN,
        windows=(1, 3, 5, 10, 20),
        columns=cols,
        sessions_cached=7,
        scope_note="Tracked desk activity only · top net buy by window",
        top_ticker_1s="AMMN",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_matrix_model_cells_and_partial():
    model = build_broker_desk_matrix_model(_result())
    assert model.broker_code == "YP"
    assert model.empty is False
    assert model.windows == (1, 3, 5, 10, 20)
    assert model.default_window == 1
    assert model.jump_ticker == "AMMN"
    # rank 0, col 0 = 1s AMMN
    c00 = model.rows[0][0]
    assert c00.ticker == "AMMN"
    assert c00.streak_label == "6s"
    assert c00.net_display.startswith("+")
    assert "6.76" in c00.net_display or "6.760" in c00.net_display
    assert c00.avg_buy_display == "@ 9,850"
    assert c00.is_default_window is True
    # partial 20s
    c20 = model.rows[0][4]
    assert c20.ticker == "AMMN"
    assert c20.is_partial is True
    assert "*(7/20)" in c20.net_display
    assert model.body_contains_action_authority() is False


def test_matrix_empty_and_scraper_text():
    model = build_broker_desk_matrix_model(None, code="AK")
    assert model.empty is True
    text = format_broker_desk_matrix_scraper_text(model)
    assert "AK" in text
    assert "Actions (TUI)" in text
    assert "top-matrix" in text or "m top" in text
