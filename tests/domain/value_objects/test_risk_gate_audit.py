"""Unit tests for Package C2 risk gate audit value objects."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.rules.risk_gate import GateContext, GateResult
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_gate_audit import (
    GateContextCompleteness,
    GateEvaluationRecord,
    build_risk_assessment_capture_dict,
    classify_gate_outcome,
)


def test_classify_pass_triggered_skipped_blocked_on_missing() -> None:
    assert (
        classify_gate_outcome(GateResult(triggered=False, reason="F-score ok", confidence=100))
        == "pass"
    )
    assert (
        classify_gate_outcome(
            GateResult(triggered=True, reason="Bandar distribution (Big Dist)", confidence=80)
        )
        == "triggered"
    )
    assert (
        classify_gate_outcome(
            GateResult(triggered=False, reason="no bandar flow data — gate skipped", confidence=0)
        )
        == "skipped"
    )
    assert (
        classify_gate_outcome(
            GateResult(triggered=True, reason="no fundamental data — gate blocked", confidence=0)
        )
        == "blocked_on_missing"
    )
    assert (
        classify_gate_outcome(
            GateResult(triggered=False, reason="no snapshot for technical gate", confidence=0)
        )
        == "skipped"
    )


def test_gate_context_completeness_missingness() -> None:
    ctx = GateContext(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 16),
        piotroski_f_score=None,
        market_cap_idr=1_000_000_000_000,
        free_float_pct=20.0,
        five_day_accdist=None,
        recent_candles=(),
        latest_snapshot=None,
    )
    completeness = GateContextCompleteness.from_context(ctx)
    missing = completeness.missingness
    assert missing["piotroski_f_score"] is True
    assert missing["market_cap_idr"] is False
    assert missing["five_day_accdist"] is True
    assert missing["recent_candles"] is True
    assert missing["latest_snapshot"] is True
    payload = completeness.to_dict()
    assert payload["recent_candles_count"] == 0
    assert payload["missingness"]["free_float_pct"] is False


def test_build_risk_assessment_capture_dict_includes_c2_blocks() -> None:
    assessment = RiskAssessment(
        rationale=("all gates passed",),
        snapshot_date=date(2026, 7, 16),
        indicators=IndicatorSnapshot(
            date=date(2026, 7, 16),
            sma=Decimal("1"),
            ema=Decimal("1"),
            rsi=Decimal("50"),
        ),
        gate_triggered=None,
    )
    evals = (
        GateEvaluationRecord.from_result(
            gate_name="FundamentalGate",
            tier="structural",
            order=0,
            result=GateResult(triggered=False, reason="ok", confidence=100),
        ),
        GateEvaluationRecord.not_evaluated(
            gate_name="BandarGate",
            tier="execution",
            order=3,
        ),
    )
    completeness = GateContextCompleteness.from_context(
        GateContext(ticker="BBCA", snapshot_date=date(2026, 7, 16))
    )
    payload = build_risk_assessment_capture_dict(
        assessment,
        gate_evaluations=evals,
        gate_context=completeness,
    )
    assert payload["gate_triggered"] is None
    assert len(payload["gate_evaluations"]) == 2
    assert payload["gate_evaluations"][0]["outcome"] == "pass"
    assert payload["gate_evaluations"][1]["outcome"] == "not_evaluated"
    assert payload["gate_context"]["ticker"] == "BBCA"
    assert "missingness" in payload["gate_context"]
