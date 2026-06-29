"""
Phase C tests — RiskAssessment.gate_triggered field.

Verifies:
- gate_triggered is absent (None) by default — backward-compatible
- gate_triggered is set on the domain value object when a gate fires
- AssessRiskResponse.gate_triggered delegates to assessment.gate_triggered
"""

from datetime import date
from decimal import Decimal

import pytest

from src.application.use_case.assess_risk_use_case import (
    AssessRiskRequest,
    AssessRiskResponse,
    AssessRiskUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import SignalSensitivity

_TODAY = date(2026, 6, 23)
_1T = 1_000_000_000_000


# ─── RiskAssessment field contract ────────────────────────────────────────────


class TestRiskAssessmentGateTriggeredField:
    """Verify the new domain field — backward compat and value contract."""

    def _make_assessment(self, gate_triggered=None) -> RiskAssessment:
        snapshot = IndicatorSnapshot(
            date=_TODAY,
            sma=Decimal("5000"),
            ema=Decimal("5000"),
            rsi=Decimal("50"),
        )
        return RiskAssessment(
            sensitivity=SignalSensitivity.BALANCED,
            rationale=("test",),
            snapshot_date=_TODAY,
            indicators=snapshot,
            gate_triggered=gate_triggered,
        )

    def test_defaults_to_none(self):
        """Existing callers omitting gate_triggered get None — backward compat."""
        snapshot = IndicatorSnapshot(
            date=_TODAY,
            sma=Decimal("5000"),
            ema=Decimal("5000"),
            rsi=Decimal("50"),
        )
        assessment = RiskAssessment(
            sensitivity=SignalSensitivity.BALANCED,
            rationale=("test",),
            snapshot_date=_TODAY,
            indicators=snapshot,
            # gate_triggered omitted — must default to None
        )
        assert assessment.gate_triggered is None

    def test_stores_gate_name_when_set(self):
        assessment = self._make_assessment(gate_triggered="FundamentalGate")
        assert assessment.gate_triggered == "FundamentalGate"

    def test_immutable_frozen_dataclass(self):
        assessment = self._make_assessment(gate_triggered="LiquidityGate")
        with pytest.raises(Exception):  # FrozenInstanceError
            assessment.gate_triggered = "other"  # type: ignore[misc]


# ─── AssessRiskResponse.gate_triggered property ───────────────────────────────


class _MockRepo(MarketDataRepository):
    def __init__(self, candles):
        self._candles = candles

    def save_candles(self, candles):
        self._candles.extend(candles)

    def get_candles(self, ticker, start_date=None, end_date=None):
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            rows = [c for c in rows if c.date >= start_date]
        if end_date:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker, start_date, end_date):
        return bool(self.get_candles(ticker, start_date, end_date))

    def get_date_range(self, ticker):
        rows = self.get_candles(ticker)
        return (rows[0].date, rows[-1].date) if rows else None


def _flat_candles(count=365, price=5000.0):
    from datetime import timedelta

    return [
        Candle(
            ticker="BBCA",
            date=_TODAY - timedelta(days=count - i),
            open=Decimal(str(price)),
            high=Decimal(str(price)),
            low=Decimal(str(price)),
            close=Decimal(str(price)),
            volume=2_000_000,
        )
        for i in range(count)
    ]


class TestAssessRiskResponseGateProperty:
    """AssessRiskResponse.gate_triggered must delegate to assessment — no duplication."""

    def test_gate_triggered_property_reads_from_assessment(self):
        """gate_triggered on response derives from the domain object, not a separate field."""
        uc = AssessRiskUseCase(
            repository=_MockRepo(_flat_candles()),
            structural_gates=[FundamentalGate()],
        )
        req = AssessRiskRequest(
            ticker="BBCA",
            sensitivity="balanced",
            gate_context=GateContext(
                ticker="BBCA",
                snapshot_date=_TODAY,
                piotroski_f_score=1,  # distressed → FundamentalGate fires
            ),
        )
        resp = uc.execute(req)

        # Both access paths must agree
        assert resp.gate_triggered == resp.assessment.gate_triggered
        assert resp.gate_triggered == "FundamentalGate"

    def test_no_gate_triggered_when_no_gate_fires(self):
        uc = AssessRiskUseCase(
            repository=_MockRepo(_flat_candles()),
            structural_gates=[FundamentalGate()],
        )
        req = AssessRiskRequest(
            ticker="BBCA",
            sensitivity="balanced",
            gate_context=GateContext(
                ticker="BBCA",
                snapshot_date=_TODAY,
                piotroski_f_score=8,  # healthy — gate passes
            ),
        )
        resp = uc.execute(req)

        assert resp.gate_triggered is None
        assert resp.assessment.gate_triggered is None

    def test_liquidity_gate_sets_gate_triggered_on_domain_object(self):
        uc = AssessRiskUseCase(
            repository=_MockRepo(_flat_candles()),
            structural_gates=[LiquidityGate()],
        )
        req = AssessRiskRequest(
            ticker="BBCA",
            sensitivity="balanced",
            gate_context=GateContext(
                ticker="BBCA",
                snapshot_date=_TODAY,
                market_cap_idr=500_000_000_000,  # 500B < 1T → third-liner
            ),
        )
        resp = uc.execute(req)

        assert resp.assessment.gate_triggered == "LiquidityGate"
        assert resp.gate_triggered == "LiquidityGate"  # property derives from domain
