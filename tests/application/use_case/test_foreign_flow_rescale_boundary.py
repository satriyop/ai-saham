"""
Boundary-case regression tests for the 0-120 -> 0-100 foreign_flow_score
rescale (ADR-039).

Proportional-preserve conversion (÷1.2) keeps pass/fail behavior identical
for every existing candidate, but only up to 1-decimal rounding. These tests
pin the new gate/bucket boundaries exactly at their converted values so any
future drift away from the ADR-039 calibration table is caught immediately.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.dto.accumulation_audit import AuditBucketPolicy
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_audit_statistics import _range_bucket
from src.application.use_case.evaluate_swing_setup_use_case import (
    COILED_SPRING_SETUP,
    FOREIGN_BOUNCE_SETUP,
    PULLBACK_CONTINUATION_SETUP,
    SMART_MONEY_CONFIRMED_SETUP,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    SwingSetupCatalogConfig,
)
from src.domain.value_objects.setup_evaluation import SetupMatch


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=5 / 7,
        total_net_value=Decimal("10000000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1030"),
        current_price=Decimal("1000"),
        vwap_discount_pct=3.0,
        rsi=45.0,
        trend="SIDE",
        foreign_flow_score=70.0,
        top_brokers=["AK", "BK"],
        institutional_flag=True,
        avg_flow_ratio=6.0,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _evaluate(setup_name: str, candidate: AccumulationCandidate, **broker_kwargs):
    return EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=setup_name,
            candidate=candidate,
            config=SwingSetupCatalogConfig(),
            **broker_kwargs,
        )
    )


def test_foreign_bounce_gate_passes_at_new_boundary_58_3():
    evaluation = _evaluate(FOREIGN_BOUNCE_SETUP, _candidate(foreign_flow_score=58.3))
    assert evaluation.match == SetupMatch.MATCH


def test_foreign_bounce_gate_fails_score_just_below_new_boundary():
    evaluation = _evaluate(
        FOREIGN_BOUNCE_SETUP,
        _candidate(
            foreign_flow_score=58.2,
            rsi=75.0,
            trend="UP",
            avg_flow_ratio=1.0,
            vwap_discount_pct=0.5,
        ),
    )
    assert evaluation.match == SetupMatch.NO_MATCH


def test_coiled_spring_gate_passes_at_new_boundary_50_0():
    evaluation = _evaluate(
        COILED_SPRING_SETUP,
        _candidate(foreign_flow_score=50.0, bb_width_pctile=0.12, avg_flow_ratio=3.5, rsi=58.0),
    )
    assert evaluation.match == SetupMatch.MATCH


def test_pullback_continuation_gate_passes_at_new_boundary_45_8():
    evaluation = _evaluate(
        PULLBACK_CONTINUATION_SETUP,
        _candidate(
            foreign_flow_score=45.8,
            trend="UP",
            avg_flow_ratio=3.0,
            rsi=50.0,
            vwap_discount_pct=-1.0,
        ),
    )
    assert evaluation.match == SetupMatch.MATCH


def test_smart_money_confirmed_gate_passes_at_new_boundary_50_0():
    from types import SimpleNamespace

    broker_detail = SimpleNamespace(
        smart_flow=Decimal("70000000"),
        noise_flow=Decimal("20000000"),
        neutral_flow=Decimal("10000000"),
        smart_share_pct=70.0,
    )
    evaluation = _evaluate(
        SMART_MONEY_CONFIRMED_SETUP,
        _candidate(foreign_flow_score=50.0),
        broker_detail=broker_detail,
    )
    assert evaluation.match == SetupMatch.MATCH


def test_audit_bucket_edges_partition_at_33_3_and_58_3():
    policy = AuditBucketPolicy()
    assert policy.foreign_flow_score == (33.3, 58.3)
    assert _range_bucket(25.0, policy.foreign_flow_score) == "<33.3"
    assert _range_bucket(33.3, policy.foreign_flow_score) == "33.3-58.3"
    assert _range_bucket(58.3, policy.foreign_flow_score) == "58.3+"
    assert _range_bucket(75.0, policy.foreign_flow_score) == "58.3+"
