"""Broker desk-home pure model — Stage 1 cockpit redesign."""

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
        top_buy_stocks=(
            SimpleNamespace(ticker="AMMN", net_value=Decimal("6760000000")),
            SimpleNamespace(ticker="BUMI", net_value=Decimal("5540000000")),
        ),
        top_sell_stocks=(SimpleNamespace(ticker="BBCA", net_value=Decimal("-1200000000")),),
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


def test_build_desk_home_surfaces_day_net_and_pulse():
    model = build_broker_desk_home_model(_show_result(), pulse=_pulse())
    assert model.broker_code == "YP"
    assert model.empty is False
    assert model.day_net_sign == "+"
    assert "11.46" in model.day_net_amount  # format_value B scale
    assert model.day_net_tone == "pos"
    assert "desk YP only" in model.day_net_sub
    assert "not full market" in model.day_net_sub.lower()
    keys = {s.key: s.value for s in model.side_stats}
    assert "Net5" in keys
    assert "38.20" in keys["Net5"] or "38.2" in keys["Net5"]
    assert "4" in keys["Buy streak"]
    assert "Δ1" in keys
    assert keys["Top buy"] == "AMMN"
    assert model.jump_ticker == "AMMN"
    assert model.top_buy[0].ticker == "AMMN"
    assert model.top_sell[0].ticker == "BBCA"
    assert "t " in model.hub_keys and "m " in model.hub_keys
    assert "f " in model.hub_keys and "h " in model.hub_keys
    assert model.hub_keys == HUB_KEY_LEGEND


def test_desk_home_has_no_action_authority():
    model = build_broker_desk_home_model(_show_result(), pulse=_pulse())
    assert model.body_contains_action_authority() is False
    scrapers = format_broker_desk_home_scraper_text(model)
    upper = scrapers.upper()
    # No Action authority tokens as verdicts
    assert " ENTER" not in f" {upper}"
    assert " WATCH" not in f" {upper}" or "WATCH" not in upper.split()
    for token in ("ENTER", "WATCH", "AVOID"):
        # Allow only if accidentally in ticker (not present here)
        assert token not in upper.split()


def test_empty_desk_home_model():
    model = build_broker_desk_home_model(None, code="AK")
    assert model.empty is True
    assert model.broker_code == "AK"
    assert "fetch" in model.empty_reason.lower() or "no broker" in model.empty_reason.lower()
    text = format_broker_desk_home_scraper_text(model)
    assert "Actions (TUI)" in text
    assert "m top" in text or "m " in text


def test_negative_day_net_tone():
    model = build_broker_desk_home_model(
        _show_result(day_net_value=Decimal("-5000000000")),
        pulse=_pulse(day_net=Decimal("-5000000000"), delta1=Decimal("-100000000")),
    )
    assert model.day_net_tone == "neg"
    assert model.day_net_sign == "−"
