"""Pins how a RiskGate that *could not evaluate* is represented.

Slice 1 recorded the defect: a gate with no input data returned the same
`GateResult` shape as a gate that evaluated and passed, and nothing but the
free-text `reason` distinguished "checked and clean" from "never checked".

This module now pins the fix. `GateResult.outcome` is a typed
`GateOutcome`, so the distinction survives config that collides every numeric
field and prose that lies. `triggered` still carries only "does it block",
which stays governed by each gate's `missing_data_action`.

Companion measurement: `scripts/report_risk_gate_skip_rates.py`, which tallies
the persisted per-gate outcomes so the skip rate is comparable before/after.

Layer: Domain
"""

from dataclasses import fields
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.domain.entities.candle import Candle
from src.domain.rules.bandar_gate import BandarGate, BandarGateConfig
from src.domain.rules.free_float_gate import FreeFloatGate, FreeFloatGatePolicy
from src.domain.rules.fundamental_gate import FundamentalGate, FundamentalGatePolicy
from src.domain.rules.liquidity_gate import LiquidityGate, LiquidityGatePolicy
from src.domain.rules.risk_gate import GateContext, GateOutcome, GateResult

_TODAY = date(2026, 8, 4)


def _ctx(**overrides) -> GateContext:
    return GateContext(ticker="BBCA", snapshot_date=_TODAY, **overrides)


def _discriminable(result: GateResult) -> dict:
    """Every typed field except the human-readable reason string."""
    return {f.name: getattr(result, f.name) for f in fields(result) if f.name != "reason"}


# Each entry: (label, gate-with-colliding-confidences, missing-data ctx, evaluated-pass ctx)
_CASES = [
    (
        "fundamental",
        FundamentalGate(policy=FundamentalGatePolicy(missing_data_confidence=100)),
        _ctx(piotroski_f_score=None),
        _ctx(piotroski_f_score=9),
    ),
    (
        "free_float",
        FreeFloatGate(policy=FreeFloatGatePolicy(missing_data_confidence=100)),
        _ctx(free_float_pct=None),
        _ctx(free_float_pct=55.0),
    ),
    (
        "bandar",
        BandarGate(BandarGateConfig(missing_data_confidence=100)),
        _ctx(five_day_accdist=None),
        _ctx(five_day_accdist="Big Acc"),
    ),
]


class TestUnevaluableIsDistinctFromPass:
    """The fix: 'no data' can no longer be laundered into a silent pass."""

    def test_missing_data_is_typed_distinctly_from_an_evaluated_pass(self):
        for label, gate, missing_ctx, pass_ctx in _CASES:
            missing = gate.evaluate(missing_ctx)
            evaluated = gate.evaluate(pass_ctx)

            assert missing.outcome is GateOutcome.UNEVALUABLE, label
            assert evaluated.outcome is GateOutcome.PASS, label
            assert missing.is_unevaluable is True, label
            assert evaluated.is_unevaluable is False, label
            # Even with every other typed field deliberately collided, the
            # outcome still separates them.
            assert _discriminable(missing) != _discriminable(evaluated), label

    def test_unevaluable_still_does_not_block_under_the_default_skip_policy(self):
        """Slice 2 changes the recorded shape, not the verdict."""
        for label, gate, missing_ctx, _pass_ctx in _CASES:
            assert gate.evaluate(missing_ctx).triggered is False, label

    def test_block_policy_makes_the_unevaluable_gate_block_without_becoming_a_trigger(self):
        gate = FundamentalGate(policy=FundamentalGatePolicy(missing_data_action="block"))
        result = gate.evaluate(_ctx(piotroski_f_score=None))
        assert result.triggered is True
        # Blocking is a policy decision; the gate still asserted nothing.
        assert result.outcome is GateOutcome.UNEVALUABLE

    def test_liquidity_is_unevaluable_only_when_neither_leg_has_input(self):
        gate = LiquidityGate(policy=LiquidityGatePolicy())
        nothing = gate.evaluate(_ctx(market_cap_idr=None, recent_candles=()))
        assert nothing.outcome is GateOutcome.UNEVALUABLE
        assert nothing.triggered is False

    def test_liquidity_partial_data_names_the_leg_it_could_not_apply(self):
        """A verdict was reached, but the reason must not claim both legs passed."""
        gate = LiquidityGate(policy=LiquidityGatePolicy())
        liquid_candles = _liquid_candles()

        unknown_cap = gate.evaluate(_ctx(market_cap_idr=None, recent_candles=liquid_candles))
        known_cap = gate.evaluate(
            _ctx(market_cap_idr=50_000_000_000_000, recent_candles=liquid_candles)
        )

        assert unknown_cap.outcome is GateOutcome.PASS
        assert unknown_cap.triggered is False
        assert "market cap unknown" in unknown_cap.reason
        assert unknown_cap.reason != known_cap.reason


class TestGateOutcomeIsNotInferredFromProse:
    """Downstream classification no longer depends on parsing the reason."""

    def test_a_gate_cannot_become_unevaluable_by_accident(self):
        """Plain construction derives PASS/TRIGGERED — never UNEVALUABLE."""
        assert (
            GateResult(triggered=False, reason="no data — gate skipped", confidence=0).outcome
            is GateOutcome.PASS
        )
        assert (
            GateResult(triggered=True, reason="no data — gate blocked", confidence=0).outcome
            is GateOutcome.TRIGGERED
        )

    def test_outcome_and_triggered_cannot_contradict_each_other(self):
        with pytest.raises(ValueError):
            GateResult(triggered=False, reason="x", outcome=GateOutcome.TRIGGERED)
        with pytest.raises(ValueError):
            GateResult(triggered=True, reason="x", outcome=GateOutcome.PASS)


def _liquid_candles():
    """20 sessions comfortably above the 5B IDR/day median floor."""
    price = Decimal("1000")
    return tuple(
        Candle(
            ticker="BBCA",
            date=_TODAY - timedelta(days=offset),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=100_000_000,
        )
        for offset in range(20)
    )
