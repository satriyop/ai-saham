"""Schema v8: persist lean named setup match/failed_gates on discovery capture.

OBSERVATION_SCHEMA only — does not change ENTER/authority scoring.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
)
from src.application.services.primary_setup_family_resolver import (
    PrimarySetupFamilyResolver,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    CoiledSpringSetupConfig,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    ForeignBounceSetupConfig,
    PullbackContinuationSetupConfig,
    SmartMoneyConfirmedSetupConfig,
    SwingSetupCatalogConfig,
)
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate, SetupMatch
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)


def _candidate(**kwargs) -> AccumulationCandidate:
    defaults = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("9000"),
        current_price=Decimal("8640"),
        vwap_discount_pct=4.0,
        rsi=45.0,
        trend="SIDE",
        foreign_flow_score=80.0,
        top_brokers=["AK", "BK"],
        institutional_flag=True,
        avg_flow_ratio=6.0,
        bb_width_pctile=0.12,
    )
    defaults.update(kwargs)
    return AccumulationCandidate(**defaults)


def _catalog_match_coiled() -> SwingSetupCatalogConfig:
    return SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_max_bb_width_pctile=0.20, family="breakout"
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )


def test_schema_version_is_8():
    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION == 8


def test_fingerprint_serializes_named_setup_evaluations_lean_dict():
    evaluations = {
        "foreign-bounce": SetupEvaluation(
            name="foreign-bounce",
            match=SetupMatch.PARTIAL,
            gates=(
                SetupGate("flow score", True, "80", ">= 58"),
                SetupGate("trend", False, "UP", "SIDE"),
            ),
            failed_reasons=("trend: UP (required SIDE)",),
            family="foreign_bounce",
            entry_authority=True,
        ),
        "coiled-spring": SetupEvaluation(
            name="coiled-spring",
            match=SetupMatch.MATCH,
            gates=(SetupGate("bb width", True, "0.12", "<= 0.20"),),
            failed_reasons=(),
            family="breakout",
            entry_authority=True,
        ),
    }
    candidate = SimpleNamespace(
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
        foreign_flow_score=70.0,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.5,
        vwap_pct=2.0,
        bandar_detector=None,
        signal_assessment=None,
        trade_setup=None,
        named_setup_evaluations=evaluations,
        to_dict=lambda: {"ticker": "BBCA"},
    )
    request = SimpleNamespace(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=2,
        min_foreign_flow_score=0.0,
        min_signal_score=0.0,
        market_context=None,
    )
    payload = build_candidate_observation_payload(
        candidate=candidate,
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 10, 30, 0),
        request=request,
    )
    assert payload["schema_version"] == 8
    lean = payload["sub_signal_fingerprint"]["named_setup_evaluations"]
    assert lean["coiled-spring"] == {
        "match": "MATCH",
        "failed_gates": [],
        "match_strength": 100.0,
        "family": "breakout",
        "entry_authority": True,
    }
    assert lean["foreign-bounce"]["match"] == "PARTIAL"
    assert lean["foreign-bounce"]["failed_gates"] == ["trend"]
    assert lean["foreign-bounce"]["match_strength"] == 60.0


def test_resolver_reuses_precomputed_named_setup_evaluations_without_catalog():
    """When evals are precomputed, catalog is not required for MATCH detection."""
    resolver = PrimarySetupFamilyResolver()
    candidate = _candidate()
    named = {
        "coiled-spring": SetupEvaluation(
            name="coiled-spring",
            match=SetupMatch.MATCH,
            gates=(),
            failed_reasons=(),
            family="breakout",
        ),
        "foreign-bounce": SetupEvaluation(
            name="foreign-bounce",
            match=SetupMatch.NO_MATCH,
            gates=(),
            failed_reasons=(),
            family="foreign_bounce",
        ),
    }
    result = resolver.resolve(
        candidate=candidate,
        swing_setup_catalog=None,
        named_setup_evaluations=named,
    )
    assert result.primary_setup_family == "breakout"
    assert result.setup_family_source == "detected_screen_evidence"
    assert result.matched_setup_families == ("breakout",)


def test_evaluate_all_available_setups_covers_catalog():
    """Screen path evaluates every AVAILABLE_SWING_SETUPS entry once."""
    catalog = _catalog_match_coiled()
    candidate = _candidate(
        foreign_flow_score=62.0,
        bb_width_pctile=0.12,
        avg_flow_ratio=3.5,
        rsi=58.0,
    )
    evaluator = EvaluateSwingSetupUseCase()
    named = {
        name: evaluator.execute(
            EvaluateSwingSetupRequest(
                setup_name=name,
                candidate=candidate,
                config=catalog,
                broker_detail=None,
            )
        )
        for name in AVAILABLE_SWING_SETUPS
    }
    assert set(named) == set(AVAILABLE_SWING_SETUPS)
    assert named["coiled-spring"].match == SetupMatch.MATCH
    assert named["smart-money-confirmed"].match == SetupMatch.NO_MATCH
