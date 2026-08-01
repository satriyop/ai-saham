"""P3 lineage: Action/setup_readiness transport without synthesis or recompute."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
)
from src.application.services.accumulation_producer_readiness import (
    extract_action_from_payload,
    extract_setup_readiness_status_from_payload,
)
from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import (
    SetupPhaseReadiness,
    SetupReadinessStatus,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


def _minimal_request(**overrides):
    values = dict(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=2,
        min_accum_score=0.0,
        min_signal_score=0.0,
        market_context=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _trade_setup(action: SetupAction) -> TradeSetup:
    return TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 31),
        action=action,
        signal_score=50,
        signal_score_raw=50,
        signal_strength=SignalStrength.MODERATE,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="test",
    )


def _signal(*, readiness: SetupPhaseReadiness | None) -> SimpleNamespace:
    assessment = SimpleNamespace(
        to_dict=lambda: {"score": 50.0, "classification": "WATCH"},
        identity=SimpleNamespace(to_dict=lambda: {"artifact_id": "aid"}),
        raw_group_score=50.0,
        raw_exact_score=50.0,
        decision_constraints=None,
    )
    return SimpleNamespace(
        assessment=assessment,
        setup_readiness=readiness,
        coverage_warning=None,
        signal_authority_coverage=None,
        active_flags=(),
        flag_adjustment=0.0,
        raw_group_score=50.0,
        raw_exact_score=50.0,
        alpha_trigger_score=None,
    )


def _candidate(*, action: SetupAction, readiness: SetupPhaseReadiness | None) -> SimpleNamespace:
    signal = _signal(readiness=readiness)
    trade = _trade_setup(action)
    return SimpleNamespace(
        ticker="BBCA",
        window_days=7,
        net_buy_days=4,
        total_days=7,
        net_buy_ratio=0.7,
        total_net_value=Decimal("1000000"),
        consecutive_streak=2,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=55.0,
        trend="UP",
        accum_score=70.0,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.5,
        vwap_pct=2.0,
        bandar_detector=None,
        signal_assessment=signal,
        trade_setup=trade,
        atr=None,
        atr_pct=None,
        to_dict=lambda: {"ticker": "BBCA", "setup_family": None},
    )


def test_evaluator_returns_none_when_family_missing_not_synthetic_ready() -> None:
    result = SetupPhaseReadinessEvaluator().evaluate(
        setup_family=None,
        setup_evidence=None,
        setup_phase=SetupPhaseSnapshot(
            current_phase=SetupPhaseState.NONE,
            previous_phase=None,
            phase_age_sessions=0,
            phase_detection_strength=0.0,
            phase_input_coverage=0.0,
            sequence_valid=None,
            reasons=("none",),
            unavailable_evidence_reasons=(),
            history=(),
        ),
    )
    assert result is None


def test_payload_preserves_computed_readiness_and_action() -> None:
    readiness = SetupPhaseReadiness(
        setup_family="breakout",
        status=SetupReadinessStatus.INELIGIBLE,
        current_phase=SetupPhaseState.FAILED,
        failed_requirements=("phase:FAILED",),
    )
    cand = _candidate(action=SetupAction.AVOID, readiness=readiness)
    payload = build_candidate_observation_payload(
        candidate=cand,
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        snapshot_date=date(2026, 7, 31),
        captured_at=datetime(2026, 7, 31, 12, 0, 0),
        request=_minimal_request(),
    )
    assert payload["trade_setup"]["action"] == "AVOID"
    assert payload["signal"]["setup_readiness"]["status"] == "INELIGIBLE"
    assert payload["signal"]["setup_readiness"]["setup_family"] == "breakout"

    session_like = {
        "canonical_window": 7,
        "features_by_window": {"7": payload, "30": payload, "90": payload},
    }
    assert extract_action_from_payload(session_like) == "AVOID"
    assert extract_setup_readiness_status_from_payload(session_like) == "INELIGIBLE"


def test_payload_preserves_null_readiness_without_synthesis() -> None:
    cand = _candidate(action=SetupAction.WATCH, readiness=None)
    payload = build_candidate_observation_payload(
        candidate=cand,
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        snapshot_date=date(2026, 7, 31),
        captured_at=datetime(2026, 7, 31, 12, 0, 0),
        request=_minimal_request(),
    )
    assert payload["signal"]["setup_readiness"] is None
    session_like = {
        "canonical_window": 7,
        "features_by_window": {"7": payload, "30": payload, "90": payload},
    }
    assert extract_setup_readiness_status_from_payload(session_like) is None
    assert extract_action_from_payload(session_like) == "WATCH"


def test_status_extractors_read_frozen_payload_only() -> None:
    frozen = {
        "canonical_window": 7,
        "features_by_window": {
            "7": {
                "trade_setup": {"action": "BLOCKED_STRUCTURAL"},
                "signal": {
                    "setup_readiness": {
                        "status": "UNAVAILABLE",
                        "setup_family": "pullback",
                    }
                },
            },
            "30": {},
            "90": {},
        },
    }
    assert extract_action_from_payload(frozen) == "BLOCKED_STRUCTURAL"
    assert extract_setup_readiness_status_from_payload(frozen) == "UNAVAILABLE"
