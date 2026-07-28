"""Tests for swing_trade_plan artifact (ADR-054 S5)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.domain.value_objects.swing_trade_plan import (
    SWING_TRADE_PLAN_ARTIFACT_TYPE,
    SwingTradePlan,
    compute_plan_id,
)


def _plan(**overrides) -> SwingTradePlan:
    base = dict(
        ticker="BBCA",
        as_of=date(2026, 7, 28),
        horizon="swing",
        action="WATCH",
        action_source="screen_judgment",
        entry_price=Decimal("6225"),
        stop_price=Decimal("6000"),
        target_price=Decimal("6500"),
        lots=10,
        capital=Decimal("10000000"),
        risk_pct=Decimal("1"),
        risk_amount=Decimal("100000"),
        setup_name="foreign-bounce",
        setup_match="MATCH",
        max_hold_days=10,
        stop_loss_pct=Decimal("5"),
        take_profit_pct=Decimal("5"),
        with_market_context=False,
        with_technical_gate=False,
        created_at=datetime(2026, 7, 28, 10, 0, tzinfo=ZoneInfo("Asia/Jakarta")),
        plan_id="abc123",
        incomplete_reason=None,
    )
    base.update(overrides)
    return SwingTradePlan(**base)


def test_round_trip_dict() -> None:
    plan = _plan()
    restored = SwingTradePlan.from_dict(plan.to_dict())
    assert restored.ticker == "BBCA"
    assert restored.entry_price == Decimal("6225")
    assert restored.lots == 10
    assert restored.is_complete is True
    assert restored.to_dict()["artifact_type"] == SWING_TRADE_PLAN_ARTIFACT_TYPE


def test_incomplete_without_lots() -> None:
    plan = _plan(lots=None, incomplete_reason="sizing_unavailable")
    assert plan.is_complete is False


def test_compute_plan_id_stable() -> None:
    payload = {"ticker": "BBCA", "as_of": "2026-07-28", "x": 1}
    assert compute_plan_id(payload) == compute_plan_id(payload)
    assert compute_plan_id(payload) != compute_plan_id({**payload, "x": 2})
