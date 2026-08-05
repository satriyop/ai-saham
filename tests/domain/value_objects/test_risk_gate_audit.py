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
            GateResult.unevaluable(reason="no bandar flow data — gate skipped", confidence=0)
        )
        == "skipped"
    )
    assert (
        classify_gate_outcome(
            GateResult.unevaluable(
                reason="no fundamental data — gate blocked",
                confidence=0,
                blocks=True,
            )
        )
        == "blocked_on_missing"
    )
    assert (
        classify_gate_outcome(
            GateResult.unevaluable(reason="no snapshot for technical gate", confidence=0)
        )
        == "skipped"
    )


def test_classify_does_not_read_the_reason_prose() -> None:
    """A real verdict is never reclassified because its wording resembles a skip."""
    # Reads like a skip, is a real evaluated pass.
    assert (
        classify_gate_outcome(
            GateResult(triggered=False, reason="no distribution — gate skipped", confidence=0)
        )
        == "pass"
    )
    # Reads like a missing-data block, is a real trigger.
    assert (
        classify_gate_outcome(
            GateResult(triggered=True, reason="no bandar flow data — gate blocked", confidence=80)
        )
        == "triggered"
    )
    # Says nothing at all, but is typed unevaluable.
    assert classify_gate_outcome(GateResult.unevaluable(reason="", confidence=0)) == "skipped"


def test_unevaluable_record_is_flagged_and_not_evaluated_is_not() -> None:
    unevaluable = GateEvaluationRecord.from_result(
        gate_name="FundamentalGate",
        tier="structural",
        order=0,
        result=GateResult.unevaluable(reason="no fundamental data — gate skipped"),
    )
    blocked = GateEvaluationRecord.from_result(
        gate_name="FreeFloatGate",
        tier="structural",
        order=1,
        result=GateResult.unevaluable(reason="unavailable — gate blocked", blocks=True),
    )
    passed = GateEvaluationRecord.from_result(
        gate_name="LiquidityGate",
        tier="structural",
        order=2,
        result=GateResult(triggered=False, reason="ok", confidence=100),
    )
    never_ran = GateEvaluationRecord.not_evaluated(
        gate_name="BandarGate", tier="execution", order=3
    )

    assert unevaluable.is_unevaluable is True
    assert blocked.is_unevaluable is True
    assert passed.is_unevaluable is False
    # "never ran" is a different fact from "ran with no input".
    assert never_ran.is_unevaluable is False


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
