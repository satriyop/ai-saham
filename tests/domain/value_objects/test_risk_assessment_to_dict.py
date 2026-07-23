"""Tests for RiskAssessment.to_dict()."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


def test_risk_assessment_to_dict_includes_required_keys() -> None:
    snapshot = IndicatorSnapshot(
        date=date(2026, 7, 10),
        sma=Decimal("1000"),
        ema=Decimal("1010"),
        rsi=Decimal("55.5"),
        extras=(("fast_ema", Decimal("1005")), ("note", "ok")),
    )
    assessment = RiskAssessment(
        rationale=("gate fired",),
        snapshot_date=date(2026, 7, 10),
        indicators=snapshot,
        gate_triggered="LiquidityGate",
        gate_is_structural=True,
        gate_confidence=80,
    )

    payload = assessment.to_dict()

    assert payload["snapshot_date"] == "2026-07-10"
    assert payload["gate_triggered"] == "LiquidityGate"
    assert payload["gate_is_structural"] is True
    assert payload["gate_confidence"] == 80
    assert payload["confidence"] == 80
    assert payload["rationale"] == ["gate fired"]
    assert payload["indicators"]["date"] == "2026-07-10"
    assert payload["indicators"]["sma"] == "1000"
    assert payload["indicators"]["ema"] == "1010"
    assert payload["indicators"]["rsi"] == "55.5"
    assert payload["indicators"]["extras"] == [["fast_ema", "1005"], ["note", "ok"]]
