"""Pins how a RiskGate that *could not evaluate* is represented.

Baseline (pre-fix) contract, recorded deliberately so the fix's diff is legible:
a gate with no input data returns the same `GateResult` shape as a gate that
evaluated and passed. Nothing but the free-text `reason` distinguishes
"checked and clean" from "never checked", and downstream code that reads the
typed fields cannot tell them apart.

Companion measurement: `scripts/report_risk_gate_skip_rates.py`, which tallies
the persisted per-gate outcomes so the skip rate is comparable before/after.

Layer: Domain
"""

from dataclasses import fields
from datetime import date, timedelta
from decimal import Decimal

from src.domain.entities.candle import Candle
from src.domain.rules.bandar_gate import BandarGate, BandarGateConfig
from src.domain.rules.free_float_gate import FreeFloatGate, FreeFloatGatePolicy
from src.domain.rules.fundamental_gate import FundamentalGate, FundamentalGatePolicy
from src.domain.rules.liquidity_gate import LiquidityGate, LiquidityGatePolicy
from src.domain.rules.risk_gate import GateContext, GateResult

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


class TestUnevaluableIsIndistinguishableFromPass:
    """The defect this task fixes: 'no data' is laundered into a silent pass."""

    def test_missing_data_is_typed_identically_to_an_evaluated_pass(self):
        for label, gate, missing_ctx, pass_ctx in _CASES:
            missing = gate.evaluate(missing_ctx)
            evaluated = gate.evaluate(pass_ctx)

            assert missing.triggered is False, label
            assert evaluated.triggered is False, label
            # Confidence is the only numeric tell, and config can collide it.
            assert _discriminable(missing) == _discriminable(evaluated), label
            # Only the free-text reason carries the distinction.
            assert missing.reason != evaluated.reason, label

    def test_liquidity_reports_a_full_pass_when_market_cap_was_never_checked(self):
        """Partial-data variant: the market-cap leg is skipped but the reason claims it passed."""
        gate = LiquidityGate(policy=LiquidityGatePolicy())
        liquid_candles = _liquid_candles()

        unknown_cap = gate.evaluate(_ctx(market_cap_idr=None, recent_candles=liquid_candles))
        known_cap = gate.evaluate(
            _ctx(market_cap_idr=50_000_000_000_000, recent_candles=liquid_candles)
        )

        assert unknown_cap.triggered is False
        assert _discriminable(unknown_cap) == _discriminable(known_cap)
        assert unknown_cap.reason == known_cap.reason


class TestSkipReasonStringsAreTheOnlySignal:
    """Downstream classification currently depends on parsing prose."""

    def test_reason_text_is_the_sole_carrier_of_the_skip(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski_f_score=None))
        assert "skipped" in result.reason
        assert result.triggered is False


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
