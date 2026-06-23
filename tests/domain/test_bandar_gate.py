"""Tests for BandarGate — execution gate for institutional distribution conflict."""

from datetime import date

from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.risk_signal import RiskLevel

_TODAY = date(2026, 6, 23)


def _ctx(five_day: str | None, is_distributing: bool = False) -> GateContext:
    return GateContext(
        ticker="BBCA",
        snapshot_date=_TODAY,
        five_day_accdist=five_day,
        bandar_is_distributing=is_distributing,
    )


class TestBandarGateConditionalOnLowRisk:
    """Gate must only fire when technical signal is LOW_RISK."""

    def test_fires_on_low_risk_with_distribution(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Big Dist", is_distributing=True), current_risk=RiskLevel.LOW_RISK
        )
        assert result.triggered
        assert result.override_risk == RiskLevel.MODERATE

    def test_does_not_fire_on_moderate_with_distribution(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Big Dist", is_distributing=True), current_risk=RiskLevel.MODERATE
        )
        assert not result.triggered

    def test_does_not_fire_on_high_risk_with_distribution(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Small Dist", is_distributing=True), current_risk=RiskLevel.HIGH_RISK
        )
        assert not result.triggered


class TestBandarGateAccumulationPasses:
    def test_accumulation_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Big Acc", is_distributing=False), current_risk=RiskLevel.LOW_RISK
        )
        assert not result.triggered

    def test_neutral_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Neutral", is_distributing=False), current_risk=RiskLevel.LOW_RISK
        )
        assert not result.triggered


class TestBandarGateNoData:
    def test_missing_five_day_passes_silently(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx(None, is_distributing=False), current_risk=RiskLevel.LOW_RISK)
        assert not result.triggered
        assert result.confidence == 0

    def test_missing_five_day_does_not_fire_even_if_distributing_flag_set(self):
        # bandar_is_distributing=True but five_day_accdist=None → still passes
        # (five_day_accdist=None is authoritative over the flag)
        gate = BandarGate()
        result = gate.evaluate(_ctx(None, is_distributing=True), current_risk=RiskLevel.LOW_RISK)
        assert not result.triggered


class TestBandarGateConfidenceAndReason:
    def test_triggered_has_reduced_confidence(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Big Dist", is_distributing=True), current_risk=RiskLevel.LOW_RISK
        )
        assert result.confidence == 50  # downgrade is conditional, not certain

    def test_triggered_reason_includes_accdist_label(self):
        gate = BandarGate()
        result = gate.evaluate(
            _ctx("Big Dist", is_distributing=True), current_risk=RiskLevel.LOW_RISK
        )
        assert "Big Dist" in result.reason
