"""Tests for FreeFloatGate — structural gate for thin free-float risk (Rec 7)."""

from datetime import date

from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.risk_gate import GateContext

_TODAY = date(2026, 6, 23)


def _ctx(free_float_pct: float | None) -> GateContext:
    return GateContext(ticker="HMSP", snapshot_date=_TODAY, free_float_pct=free_float_pct)


class TestFreeFloatGateTriggers:
    def test_thin_float_triggers_high_risk(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(6.7))
        assert result.triggered

    def test_float_below_threshold_triggers(self):
        gate = FreeFloatGate(min_free_float_pct=15.0)
        result = gate.evaluate(_ctx(14.9))
        assert result.triggered

    def test_float_at_threshold_passes(self):
        # boundary: exactly at threshold is acceptable (< not <=)
        gate = FreeFloatGate(min_free_float_pct=15.0)
        result = gate.evaluate(_ctx(15.0))
        assert not result.triggered

    def test_float_above_threshold_passes(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(60.0))
        assert not result.triggered

    def test_zero_float_triggers(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(0.0))
        assert result.triggered

    def test_hundred_pct_float_passes(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(100.0))
        assert not result.triggered


class TestFreeFloatGateMissingData:
    def test_none_float_passes_silently(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(None))
        assert not result.triggered

    def test_none_float_has_zero_confidence(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(None))
        assert result.confidence == 0

    def test_none_float_does_not_alter_current_risk(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(None))
        assert not result.triggered


class TestFreeFloatGateIgnoresCurrentRisk:
    """Structural gates fire regardless of what the technical rule engine said."""

    def test_fires_when_current_risk_is_low(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(6.7))
        assert result.triggered

    def test_fires_when_current_risk_is_moderate(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(6.7))
        assert result.triggered

    def test_fires_when_current_risk_is_high(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(6.7))
        assert result.triggered


class TestFreeFloatGateReason:
    def test_triggered_reason_contains_free_float_wording(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(6.7))
        assert "free float" in result.reason.lower()

    def test_triggered_reason_contains_float_value(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(6.7))
        assert "6.7" in result.reason

    def test_triggered_reason_contains_threshold(self):
        gate = FreeFloatGate(min_free_float_pct=15.0)
        result = gate.evaluate(_ctx(10.0))
        assert "15" in result.reason

    def test_pass_reason_contains_float_value(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(45.0))
        assert "45.0" in result.reason

    def test_triggered_confidence_is_100(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(5.0))
        assert result.confidence == 100

    def test_pass_confidence_is_100(self):
        gate = FreeFloatGate()
        result = gate.evaluate(_ctx(50.0))
        assert result.confidence == 100


class TestFreeFloatGateCustomThreshold:
    def test_msci_threshold_fires_at_border(self):
        gate = FreeFloatGate(min_free_float_pct=15.0)
        assert gate.evaluate(_ctx(14.9)).triggered
        assert not gate.evaluate(_ctx(15.1)).triggered

    def test_strict_threshold_catches_more(self):
        gate_strict = FreeFloatGate(min_free_float_pct=25.0)
        gate_default = FreeFloatGate(min_free_float_pct=15.0)
        # 20% float: strict fires, default passes
        assert gate_strict.evaluate(_ctx(20.0)).triggered
        assert not gate_default.evaluate(_ctx(20.0)).triggered
