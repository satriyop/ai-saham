"""ADR-054 S3: screen TradeSetup is authoritative unless recompute allowed."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.application.services.swing_judgment_authority import (
    SCREEN_JUDGMENT_WARNING,
    allow_action_recompute,
    resolve_authoritative_trade_setup,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


def _setup(action: SetupAction, *, ticker: str = "BBCA") -> TradeSetup:
    return TradeSetup(
        ticker=ticker,
        snapshot_date=date(2026, 7, 28),
        action=action,
        signal_score=70,
        signal_score_raw=70,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="test",
    )


def test_allow_action_recompute_only_with_explicit_flags() -> None:
    assert allow_action_recompute(with_market_context=False, with_technical_gate=False) is False
    assert allow_action_recompute(with_market_context=True, with_technical_gate=False) is True
    assert allow_action_recompute(with_market_context=False, with_technical_gate=True) is True


def test_inherits_screen_setup_when_recompute_false() -> None:
    screen = _setup(SetupAction.WATCH)
    plan = _setup(SetupAction.ENTER)
    candidate = SimpleNamespace(trade_setup=screen)
    resolved, note = resolve_authoritative_trade_setup(
        candidate, plan_recomputed=plan, allow_recompute=False
    )
    assert resolved is screen
    assert resolved is not None
    assert resolved.action == SetupAction.WATCH
    assert note == SCREEN_JUDGMENT_WARNING


def test_uses_plan_when_recompute_true() -> None:
    screen = _setup(SetupAction.WATCH)
    plan = _setup(SetupAction.ENTER)
    candidate = SimpleNamespace(trade_setup=screen)
    resolved, note = resolve_authoritative_trade_setup(
        candidate, plan_recomputed=plan, allow_recompute=True
    )
    assert resolved is plan
    assert resolved is not None
    assert resolved.action == SetupAction.ENTER
    assert note is None


def test_fallback_to_plan_when_screen_missing() -> None:
    plan = _setup(SetupAction.BLOCKED_STRUCTURAL)
    resolved, note = resolve_authoritative_trade_setup(
        SimpleNamespace(trade_setup=None),
        plan_recomputed=plan,
        allow_recompute=False,
    )
    assert resolved is plan
    assert note is None


def test_none_candidate_falls_back_to_plan() -> None:
    plan = _setup(SetupAction.ENTER)
    resolved, note = resolve_authoritative_trade_setup(
        None, plan_recomputed=plan, allow_recompute=False
    )
    assert resolved is plan
    assert note is None
