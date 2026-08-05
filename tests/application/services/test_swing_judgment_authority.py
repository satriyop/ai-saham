"""ADR-054 S3 / ADR-067 §3: screen TradeSetup is authoritative, always."""

from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace

from src.application.services import swing_judgment_authority
from src.application.services.swing_judgment_authority import (
    SCREEN_JUDGMENT_WARNING,
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


def test_inherits_screen_setup_when_screen_judged() -> None:
    screen = _setup(SetupAction.WATCH)
    plan = _setup(SetupAction.ENTER)
    candidate = SimpleNamespace(trade_setup=screen)
    resolved, note = resolve_authoritative_trade_setup(candidate, plan_recomputed=plan)
    assert resolved is screen
    assert resolved is not None
    assert resolved.action == SetupAction.WATCH
    assert note == SCREEN_JUDGMENT_WARNING


def test_no_flag_can_make_plan_override_screen() -> None:
    """ADR-067 §3 negative: the recompute escape hatch is gone for good.

    `resolve_authoritative_trade_setup` must expose no keyword that lets a
    caller substitute a plan-computed Action for the screen verdict.
    """
    signature = inspect.signature(resolve_authoritative_trade_setup)
    assert set(signature.parameters) == {"candidate", "plan_recomputed"}
    assert not hasattr(swing_judgment_authority, "allow_action_recompute")

    screen = _setup(SetupAction.WATCH)
    plan = _setup(SetupAction.ENTER)
    resolved, _ = resolve_authoritative_trade_setup(
        SimpleNamespace(trade_setup=screen), plan_recomputed=plan
    )
    assert resolved is screen


def test_fallback_to_plan_when_screen_missing() -> None:
    plan = _setup(SetupAction.BLOCKED_STRUCTURAL)
    resolved, note = resolve_authoritative_trade_setup(
        SimpleNamespace(trade_setup=None),
        plan_recomputed=plan,
    )
    assert resolved is plan
    assert note is None


def test_none_candidate_falls_back_to_plan() -> None:
    plan = _setup(SetupAction.ENTER)
    resolved, note = resolve_authoritative_trade_setup(None, plan_recomputed=plan)
    assert resolved is plan
    assert note is None
