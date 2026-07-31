"""Broker flow + history models — pure paint contracts (no full-app mount).

Hub ``f`` / ``h`` navigation residual: ``test_view_broker_journey``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_flow_model import (
    build_broker_desk_flow_model,
    format_broker_desk_flow_scraper_text,
)
from src.adapters.tui.broker_desk_history_model import (
    build_broker_desk_history_model,
    format_broker_desk_history_scraper_text,
)
from src.domain.entities.broker_flow import BrokerType


def test_build_flow_model_newest_first_and_bars():
    result = SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        scope_note="Tracked desk",
        days=(
            SimpleNamespace(
                date=date(2026, 7, 28),
                net_value=Decimal("1000000000"),
                net_lot=10,
                ticker_count=2,
            ),
            SimpleNamespace(
                date=date(2026, 7, 29),
                net_value=Decimal("2000000000"),
                net_lot=20,
                ticker_count=3,
            ),
        ),
    )
    model = build_broker_desk_flow_model(result)
    assert model.empty is False
    assert model.days[0].date_label == "2026-07-29"  # newest first
    assert model.days[0].bar_pct == 100
    assert model.days[1].bar_pct == 50
    assert model.days[0].net_display.startswith("+")
    assert "not market foreign" in model.scope_note
    assert model.body_contains_action_authority() is False
    assert "Flow" in format_broker_desk_flow_scraper_text(model)


def test_build_history_model_rows():
    result = SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.LOCAL,
        scope_note="Tracked desk",
        pinned_ticker=None,
        flows=(
            SimpleNamespace(
                date=date(2026, 7, 29),
                ticker="AMMN",
                net_value=Decimal("5000000000"),
                net_lot=100,
            ),
            SimpleNamespace(
                date=date(2026, 7, 28),
                ticker="BBCA",
                net_value=Decimal("-1000000000"),
                net_lot=-20,
            ),
        ),
    )
    model = build_broker_desk_history_model(result)
    assert model.rows[0].ticker == "AMMN"
    assert model.rows[0].tone == "pos"
    assert model.rows[1].ticker == "BBCA"
    assert model.jump_ticker == "AMMN"
    assert model.body_contains_action_authority() is False
    assert "History" in format_broker_desk_history_scraper_text(model)


def test_flow_paint_contract_date_and_hub():
    """What #fl-date-0 paint would show after hub f."""
    model = build_broker_desk_flow_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            scope_note="Tracked",
            days=(
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    net_value=Decimal("3000000000"),
                    net_lot=50,
                    ticker_count=4,
                ),
            ),
        )
    )
    assert model.days[0].date_label == "2026-07-29"
    assert model.hub_keys
    title = f"Flow by day · {model.broker_code}"
    assert title == "Flow by day · YP"
    text = format_broker_desk_flow_scraper_text(model)
    assert "2026-07-29" in text


def test_history_paint_contract_ticker_row():
    """What #hi-t-0 paint would show after hub h."""
    model = build_broker_desk_history_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            scope_note="Tracked",
            pinned_ticker=None,
            flows=(
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    ticker="AMMN",
                    net_value=Decimal("1000000000"),
                    net_lot=10,
                ),
            ),
        )
    )
    assert model.rows[0].ticker == "AMMN"
    assert model.jump_ticker == "AMMN"
    title = f"History · {model.broker_code}"
    assert title == "History · YP"
    text = format_broker_desk_history_scraper_text(model)
    assert "AMMN" in text
