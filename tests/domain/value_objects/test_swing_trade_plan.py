"""Strict swing_trade_plan schema-v2 and handoff invariants."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.domain.value_objects.swing_trade_plan import (
    SWING_TRADE_PLAN_ARTIFACT_TYPE,
    SWING_TRADE_PLAN_SCHEMA_VERSION,
    SwingPlanJudgmentReference,
    SwingPlanJudgmentSource,
    SwingPlanJudgmentStatus,
    SwingPlanJudgmentUnavailableReason,
    SwingTradePlan,
    compute_plan_id,
)
from src.domain.value_objects.trade_setup import SetupAction


def _judgment(*, available: bool = True) -> SwingPlanJudgmentReference:
    return SwingPlanJudgmentReference(
        status=(
            SwingPlanJudgmentStatus.AVAILABLE if available else SwingPlanJudgmentStatus.UNAVAILABLE
        ),
        source=SwingPlanJudgmentSource.SCREEN_ACCUM,
        ticker="BBCA",
        snapshot_date=date(2026, 7, 28),
        action=SetupAction.WATCH if available else None,
        unavailable_reason=(
            None if available else SwingPlanJudgmentUnavailableReason.NO_SCREEN_TRADE_SETUP
        ),
    )


def _plan(**overrides) -> SwingTradePlan:
    base = dict(
        ticker="BBCA",
        as_of=date(2026, 7, 28),
        horizon="swing",
        judgment_ref=_judgment(),
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
        created_at=datetime(2026, 7, 28, 10, 0, tzinfo=ZoneInfo("Asia/Jakarta")),
        plan_id="abc123",
        incomplete_reason=None,
    )
    base.update(overrides)
    return SwingTradePlan(**base)


def test_round_trip_schema_v2() -> None:
    restored = SwingTradePlan.from_dict(_plan().to_dict())
    assert restored.geometry_complete
    assert restored.handoff_ready
    assert restored.judgment_ref.action is SetupAction.WATCH
    assert restored.to_dict()["artifact_type"] == SWING_TRADE_PLAN_ARTIFACT_TYPE
    assert restored.to_dict()["schema_version"] == SWING_TRADE_PLAN_SCHEMA_VERSION


def test_geometry_and_handoff_are_independent() -> None:
    unavailable = _plan(judgment_ref=_judgment(available=False))
    assert unavailable.geometry_complete
    assert not unavailable.handoff_ready
    incomplete = _plan(lots=None, incomplete_reason="sizing_unavailable")
    assert not incomplete.geometry_complete
    assert not incomplete.handoff_ready


@pytest.mark.parametrize("schema", [None, 1, 3, "2"])
def test_historical_and_unknown_schemas_fail_closed(schema) -> None:
    payload = _plan().to_dict()
    payload["schema_version"] = schema
    with pytest.raises(ValueError, match="unsupported swing_trade_plan schema_version"):
        SwingTradePlan.from_dict(payload)


def test_flat_legacy_payload_fails_closed() -> None:
    payload = _plan().to_dict()
    payload.pop("geometry")
    payload["entry_price"] = "6225"
    with pytest.raises(ValueError, match="geometry must be an object"):
        SwingTradePlan.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "UNKNOWN"),
        ("source", "plan_swing"),
        ("action", "BUY"),
        ("unavailable_reason", "unknown_reason"),
    ],
)
def test_malformed_judgment_enums_fail_closed(field, value) -> None:
    payload = _plan().to_dict()
    payload["judgment_ref"][field] = value
    with pytest.raises(ValueError, match="invalid swing plan judgment_ref"):
        SwingTradePlan.from_dict(payload)


def test_conflicting_judgment_status_fields_fail_closed() -> None:
    payload = _plan().to_dict()
    payload["judgment_ref"]["status"] = "UNAVAILABLE"
    payload["judgment_ref"]["unavailable_reason"] = "no_screen_trade_setup"
    with pytest.raises(ValueError, match="cannot carry an Action"):
        SwingTradePlan.from_dict(payload)


def test_direct_judgment_construction_requires_typed_status_and_source() -> None:
    with pytest.raises(TypeError, match="SwingPlanJudgmentStatus"):
        SwingPlanJudgmentReference(
            status="AVAILABLE",
            source=SwingPlanJudgmentSource.SCREEN_ACCUM,
            ticker="BBCA",
            snapshot_date=date(2026, 7, 28),
            action=SetupAction.WATCH,
        )
    with pytest.raises(TypeError, match="SwingPlanJudgmentSource"):
        SwingPlanJudgmentReference(
            status=SwingPlanJudgmentStatus.AVAILABLE,
            source="screen_accum",
            ticker="BBCA",
            snapshot_date=date(2026, 7, 28),
            action=SetupAction.WATCH,
        )


def test_cross_ticker_judgment_fails_closed() -> None:
    with pytest.raises(ValueError, match="tickers must match"):
        _plan(ticker="BBRI")


def test_compute_plan_id_stable() -> None:
    payload = {"ticker": "BBCA", "as_of": "2026-07-28", "x": 1}
    assert compute_plan_id(payload) == compute_plan_id(payload)
    assert compute_plan_id(payload) != compute_plan_id({**payload, "x": 2})
