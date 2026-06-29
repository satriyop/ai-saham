"""Tests for BandarGate — execution gate for institutional distribution conflict."""

from datetime import date

from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.risk_gate import GateContext

_TODAY = date(2026, 6, 23)


def _ctx(five_day: str | None) -> GateContext:
    return GateContext(
        ticker="BBCA",
        snapshot_date=_TODAY,
        five_day_accdist=five_day,
    )


class TestBandarGateUnconditionalOnDistribution:
    """Gate fires on distribution label regardless of technical risk level."""

    def test_fires_on_distribution_label(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Dist"))
        assert result.triggered
        assert result.confidence == 80

    def test_fires_on_small_distribution_label(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Small Dist"))
        assert result.triggered
        assert result.confidence == 80

    def test_fires_unconditionally_not_conditional_on_risk_level(self):
        """Distribution fires regardless of what technical risk would have been."""
        gate = BandarGate()
        # Previously only fired on LOW_RISK; now fires unconditionally
        result = gate.evaluate(_ctx("Big Dist"))
        assert result.triggered
        assert result.confidence == 80


class TestBandarGateAccumulationPasses:
    def test_accumulation_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Acc"))
        assert not result.triggered

    def test_neutral_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Neutral"))
        assert not result.triggered


class TestBandarGateNoData:
    def test_missing_five_day_passes_silently(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx(None))
        assert not result.triggered
        assert result.confidence == 0

    def test_missing_five_day_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx(None))
        assert not result.triggered


class TestBandarGateConfidenceAndReason:
    def test_triggered_has_confidence_80(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Dist"))
        assert result.confidence == 80  # unconditional distribution, partial confidence

    def test_triggered_reason_includes_accdist_label(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Dist"))
        assert "Big Dist" in result.reason
