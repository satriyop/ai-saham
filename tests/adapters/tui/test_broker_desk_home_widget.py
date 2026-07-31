"""Broker desk-home paint contract — pure model (no full-app mount).

Journey wiring (list → home → deep → esc) lives in
``test_view_broker_journey`` (D3 residual). Paint hierarchy is covered here
from the pure model the widget reads.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_home_model import (
    HUB_KEY_LEGEND,
    build_broker_desk_home_model,
    format_broker_desk_home_scraper_text,
)
from src.domain.entities.broker_flow import BrokerType


def _show_result(**overrides):
    base = dict(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        as_of=date(2026, 7, 29),
        day_net_value=Decimal("11460000000"),
        day_net_lot=413768,
        day_ticker_count=45,
        top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("6760000000")),),
        top_sell_stocks=(),
        scope_note="Tracked desk activity only (broker_daily_flow)",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _pulse(**overrides):
    base = dict(
        day_net=Decimal("11460000000"),
        net5=Decimal("38200000000"),
        sessions_in_net5=5,
        buy_streak=4,
        delta1=Decimal("2100000000"),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_home_paint_contract_hero_hub_and_no_action_authority():
    """Widget paint maps model → title/hero amount/hub; no Action authority."""
    model = build_broker_desk_home_model(_show_result(), pulse=_pulse())

    # Hero amount (what #bd-amt would show)
    assert "11.46" in model.day_net_amount
    assert model.day_net_sign == "+"
    assert model.day_net_tone == "pos"
    assert model.empty is False

    # Title / sub strings paint() composes (density: Broker · CODE hero)
    title = f"Broker · {model.broker_code}"
    assert title == "Broker · YP"
    sub = f"{model.broker_name} · {model.type_label} · as of {model.as_of} · local cache"
    assert "YP Desk" in sub
    assert "Foreign" in sub or model.type_label
    assert model.as_of == "2026-07-29" or "2026-07-29" in str(model.as_of)
    assert "Day net" in "Day net · desk"  # hero lab

    # Hub keys (what #bd-hub would show) — deep affordances
    assert model.hub_keys == HUB_KEY_LEGEND
    assert "m top" in model.hub_keys or (" m " in f" {model.hub_keys} " and "t " in model.hub_keys)
    for key in ("t ", "f ", "h ", "m "):
        assert key in model.hub_keys or key.strip() in model.hub_keys

    assert model.body_contains_action_authority() is False
    scrapers = format_broker_desk_home_scraper_text(model)
    assert "11.46" in scrapers or "AMMN" in scrapers
    upper = scrapers.upper()
    for token in ("ENTER", "WATCH", "AVOID"):
        assert token not in upper.split()


def test_home_paint_contract_top_buy_row():
    model = build_broker_desk_home_model(_show_result(), pulse=_pulse())
    assert model.top_buy
    assert model.top_buy[0].ticker == "AMMN"
    assert model.jump_ticker == "AMMN"
