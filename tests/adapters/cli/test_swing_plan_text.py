"""
Regression tests for swing_plan_text() setup entry-authority framing.

A setup MATCH must not be described as an actionable plan ("Setup matched.
Add --capital..." / "Consider N lots...") when DecisionPolicy has capped the
final action to WATCH on entry-authority or setup-phase grounds. The Plan
text must reflect the same TradeSetup.action shown in the Verdict panel.

Layer: Adapter (render-only, no scoring, no DecisionPolicy changes).
"""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.cli.plan_swing_display import SwingDisplayConfig, swing_plan_text


def _config() -> SwingDisplayConfig:
    return SwingDisplayConfig(
        enter_min_score=70.0,
        watch_min_score=40.0,
        coiled_spring_bb_pctile=0.20,
        coiled_spring_min_score=60.0,
        strong_min_score=70.0,
        strong_min_streak=8,
        building_min_score=60.0,
        building_min_streak=5,
        foreign_bounce_max_hold_days=10,
    )


def _setup_eval(match: str = "MATCH") -> SimpleNamespace:
    return SimpleNamespace(
        passed=(match == "MATCH"),
        match=SimpleNamespace(value=match),
        failed_reasons=(),
    )


def _trade_setup(action: str) -> SimpleNamespace:
    return SimpleNamespace(action=SimpleNamespace(value=action))


def _signal_assessment(*reasons: str) -> SimpleNamespace:
    return SimpleNamespace(
        assessment=SimpleNamespace(
            decision_constraints=SimpleNamespace(constraint_reasons=tuple(reasons))
        )
    )


def test_confirmation_only_match_reflects_watch_action_not_generic_matched_text():
    text, style = swing_plan_text(
        "INDF",
        None,
        None,
        None,
        _setup_eval("MATCH"),
        None,
        _config(),
        trade_setup=_trade_setup("WATCH"),
        signal_assessment=_signal_assessment(
            "Setup smart_money_confirmed has no standalone entry authority"
        ),
    )
    assert "Setup matched as confirmation evidence, but action is WATCH" in text
    assert "no standalone entry authority" in text
    assert "Add --capital to compute lot size" not in text
    assert style == "yellow"


def test_phase_gated_match_reflects_watch_action_even_with_capital_sizing():
    """Even when --capital produced a lot-sizing plan, a phase-gated block
    must override the misleading 'Consider N lots' framing."""
    setup_sizing = SimpleNamespace(
        lots=10, entry_price=1000, target_price=1100, stop_price=950
    )
    text, style = swing_plan_text(
        "INDF",
        10_000_000,
        None,
        None,
        _setup_eval("MATCH"),
        setup_sizing,
        _config(),
        trade_setup=_trade_setup("WATCH"),
        signal_assessment=_signal_assessment(
            "Setup foreign_bounce requires phase BREAKOUT_CONFIRMATION for "
            "ENTER; current phase ACCUMULATION"
        ),
    )
    assert "but action is WATCH" in text
    assert "requires phase BREAKOUT_CONFIRMATION" in text
    assert "Consider" not in text
    assert style == "yellow"


def test_match_without_entry_authority_block_keeps_existing_matched_text():
    """No constraint reason fired — existing 'Setup matched' framing is
    unaffected (backward compatible when trade_setup/signal_assessment absent)."""
    text, style = swing_plan_text(
        "INDF",
        None,
        None,
        None,
        _setup_eval("MATCH"),
        None,
        _config(),
    )
    assert text == "Setup matched. Add --capital to compute lot size."
    assert style == "green"


def test_match_with_enter_action_keeps_existing_matched_text():
    """A setup that legitimately reaches ENTER renders the normal matched text."""
    text, style = swing_plan_text(
        "INDF",
        None,
        None,
        None,
        _setup_eval("MATCH"),
        None,
        _config(),
        trade_setup=_trade_setup("ENTER"),
        signal_assessment=_signal_assessment(),
    )
    assert text == "Setup matched. Add --capital to compute lot size."
    assert style == "green"


def test_partial_match_unaffected_by_entry_authority_check():
    text, style = swing_plan_text(
        "INDF",
        None,
        None,
        None,
        _setup_eval("PARTIAL"),
        None,
        _config(),
        trade_setup=_trade_setup("WATCH"),
        signal_assessment=_signal_assessment(
            "Setup smart_money_confirmed has no standalone entry authority"
        ),
    )
    assert text == (
        "Setup is partial. Wait for failed gates to improve before treating it as a match."
    )
    assert style == "yellow"
