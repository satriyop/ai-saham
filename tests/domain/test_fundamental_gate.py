"""Tests for FundamentalGate — structural gate for Piotroski F-Score distress."""

from datetime import date

import pytest

from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.risk_gate import GateContext

_TODAY = date(2026, 6, 23)


def _ctx(piotroski: int | None) -> GateContext:
    return GateContext(ticker="BBCA", snapshot_date=_TODAY, piotroski_f_score=piotroski)


class TestFundamentalGateThresholds:
    def test_distressed_score_triggers_high_risk(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=2))
        assert result.triggered

    def test_score_at_threshold_triggers(self):
        gate = FundamentalGate(distress_threshold=3)
        result = gate.evaluate(_ctx(piotroski=3))
        assert result.triggered

    def test_score_above_threshold_passes(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=4))
        assert not result.triggered

    def test_score_zero_triggers(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=0))
        assert result.triggered

    def test_custom_threshold(self):
        gate = FundamentalGate(distress_threshold=5)
        assert gate.evaluate(_ctx(piotroski=5)).triggered
        assert not gate.evaluate(_ctx(piotroski=6)).triggered

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            FundamentalGate(distress_threshold=10)
        with pytest.raises(ValueError):
            FundamentalGate(distress_threshold=-1)


class TestFundamentalGateNoData:
    def test_missing_data_passes_silently(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=None))
        assert not result.triggered
        assert result.confidence == 0  # signals data absence

    def test_missing_data_does_not_alter_current_risk(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=None))
        assert not result.triggered


class TestFundamentalGateIgnoresCurrentRisk:
    """Structural gates must not depend on the technical risk level."""

    def test_fires_regardless_of_current_high_risk(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=1))
        assert result.triggered

    def test_fires_regardless_of_current_moderate(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=2))
        assert result.triggered

    def test_fires_regardless_of_current_low_risk(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=3))
        assert result.triggered


class TestFundamentalGateReason:
    def test_triggered_reason_includes_score(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=2))
        assert "2" in result.reason
        assert "3" in result.reason  # threshold

    def test_passing_reason_includes_score(self):
        gate = FundamentalGate()
        result = gate.evaluate(_ctx(piotroski=7))
        assert "7" in result.reason
