"""Broker desk top dual-heat pure model — Stage 3."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_top_model import (
    build_broker_desk_top_model,
    format_broker_desk_top_scraper_text,
)
from src.domain.entities.broker_flow import BrokerType


def _net(ticker: str, net: str, lot: int = 100):
    return SimpleNamespace(ticker=ticker, net_value=Decimal(net), net_lot=lot)


def _result(**overrides):
    base = dict(
        broker_code="YP",
        broker_name="YP Desk",
        date=date(2026, 7, 29),
        broker_type=BrokerType.FOREIGN,
        top_buy_stocks=(
            _net("AMMN", "6760000000", 500),
            _net("BUMI", "3380000000", 200),
        ),
        top_sell_stocks=(_net("BBCA", "-1200000000", -50),),
        scope_note="Tracked desk activity only (broker_daily_flow)",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_top_model_dual_sides_and_bars():
    model = build_broker_desk_top_model(_result())
    assert model.broker_code == "YP"
    assert model.empty is False
    assert model.session_date == "2026-07-29"
    assert "latest session" in model.scope_note
    assert model.jump_ticker == "AMMN"
    assert len(model.buys) == 2
    assert model.buys[0].ticker == "AMMN"
    assert model.buys[0].bar_pct == 100  # peak
    assert model.buys[1].bar_pct == 50  # half of peak
    assert model.buys[0].net_display.startswith("+")
    assert model.sells[0].ticker == "BBCA"
    assert model.sells[0].tone == "neg"
    assert model.body_contains_action_authority() is False


def test_top_empty_and_scraper():
    model = build_broker_desk_top_model(None, code="AK")
    assert model.empty is True
    text = format_broker_desk_top_scraper_text(model)
    assert "AK" in text
    assert "Net buy" in text
    assert "Actions (TUI)" in text
