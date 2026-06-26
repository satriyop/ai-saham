"""Tests for BandarGate — execution gate for institutional distribution conflict."""

from datetime import date

from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.risk_gate import GateContext

_TODAY = date(2026, 6, 23)


def _ctx(five_day: str | None, is_distributing: bool = False) -> GateContext:
    return GateContext(
        ticker="BBCA",
        snapshot_date=_TODAY,
        five_day_accdist=five_day,
        bandar_is_distributing=is_distributing,
    )


class TestBandarGateUnconditionalOnDistribution:
    """Gate fires on distribution label regardless of technical risk level."""

    def test_fires_on_distribution_label(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Dist", is_distributing=True))
        assert result.triggered
        assert result.confidence == 80

    def test_fires_on_small_distribution_label(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Small Dist", is_distributing=True))
        assert result.triggered
        assert result.confidence == 80

    def test_fires_unconditionally_not_conditional_on_risk_level(self):
        """Distribution fires regardless of what technical risk would have been."""
        gate = BandarGate()
        # Previously only fired on LOW_RISK; now fires unconditionally
        result = gate.evaluate(_ctx("Big Dist", is_distributing=True))
        assert result.triggered
        assert result.confidence == 80


class TestBandarGateAccumulationPasses:
    def test_accumulation_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Acc", is_distributing=False))
        assert not result.triggered

    def test_neutral_does_not_fire(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Neutral", is_distributing=False))
        assert not result.triggered


class TestBandarGateNoData:
    def test_missing_five_day_passes_silently(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx(None, is_distributing=False))
        assert not result.triggered
        assert result.confidence == 0

    def test_missing_five_day_does_not_fire_even_if_distributing_flag_set(self):
        # bandar_is_distributing=True but five_day_accdist=None → still passes
        # (five_day_accdist=None is authoritative over the flag)
        gate = BandarGate()
        result = gate.evaluate(_ctx(None, is_distributing=True))
        assert not result.triggered


class TestBandarGateConfidenceAndReason:
    def test_triggered_has_confidence_80(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Dist", is_distributing=True))
        assert result.confidence == 80  # unconditional distribution, partial confidence

    def test_triggered_reason_includes_accdist_label(self):
        gate = BandarGate()
        result = gate.evaluate(_ctx("Big Dist", is_distributing=True))
        assert "Big Dist" in result.reason
