"""Broker matrix desk paint contract — pure model (no full-app mount).

Hub ``m`` journey + esc trail: ``test_view_broker_journey`` (D3 residual).
"""

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


def _cell() -> DeskTickerWindowCell:
    return DeskTickerWindowCell(
        ticker="AMMN",
        net_value=Decimal("6760000000"),
        window=1,
        sessions_used=1,
        avg_buy_price=Decimal("9850"),
        buy_streak=6,
        is_partial=False,
    )


def _result():
    return SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        as_of=date(2026, 7, 29),
        broker_type=BrokerType.FOREIGN,
        windows=(1, 3, 5, 10, 20),
        columns={1: (_cell(),), 3: (), 5: (), 10: (), 20: ()},
        sessions_cached=7,
        scope_note="Tracked desk",
        top_ticker_1s="AMMN",
    )


def test_matrix_paint_contract_cell_hierarchy():
    """What #mx-c-0-0 paint would show: ticker + streak + avg buy."""
    model = build_broker_desk_matrix_model(_result())
    assert model.empty is False
    assert model.jump_ticker == "AMMN"
    assert model.broker_code == "YP"

    cell0 = model.rows[0][0]
    assert cell0 is not None and not cell0.empty
    assert cell0.ticker == "AMMN"
    assert cell0.streak_label == "6s"
    assert cell0.avg_buy_display == "@ 9,850" or "9,850" in cell0.avg_buy_display
    assert "6.76" in cell0.net_display or cell0.net_display.startswith("+")

    # Title paint composes
    title = f"Top 5 net buy · desk {model.broker_code}"
    assert "YP" in title

    assert model.body_contains_action_authority() is False
    text = format_broker_desk_matrix_scraper_text(model)
    assert "AMMN" in text
    assert "MATRIX" not in text  # structured facts, not fake loader body
