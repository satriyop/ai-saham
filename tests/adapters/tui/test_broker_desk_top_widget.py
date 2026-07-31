"""Broker top dual-heat paint contract — pure model (no full-app mount).

Hub ``t`` journey: residual full-app in ``test_view_broker_journey``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_top_model import (
    build_broker_desk_top_model,
    format_broker_desk_top_scraper_text,
)
from src.domain.entities.broker_flow import BrokerType


def _result():
    return SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        date=date(2026, 7, 29),
        broker_type=BrokerType.FOREIGN,
        top_buy_stocks=(
            SimpleNamespace(ticker="AMMN", net_value=Decimal("6760000000"), net_lot=500),
        ),
        top_sell_stocks=(
            SimpleNamespace(ticker="BBCA", net_value=Decimal("-1200000000"), net_lot=-40),
        ),
        scope_note="Tracked desk",
    )


def test_top_paint_contract_buy_and_sell_sides():
    """What #tp-buy-0 / #tp-sell-0 paint would show."""
    model = build_broker_desk_top_model(_result())
    assert model.empty is False
    assert model.jump_ticker == "AMMN"
    assert model.buys[0].ticker == "AMMN"
    assert model.sells[0].ticker == "BBCA"
    assert model.sells[0].tone == "neg"

    title = f"Buy / sell · desk {model.broker_code} · latest session"
    assert "YP" in title
    assert model.hub_keys

    assert model.body_contains_action_authority() is False
    text = format_broker_desk_top_scraper_text(model)
    assert "AMMN" in text and "BBCA" in text
