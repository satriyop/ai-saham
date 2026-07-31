"""Focused payload contract tests for accumulation policy snapshots."""

from __future__ import annotations

from src.application.services.accumulation_policy_snapshot_payloads import (
    ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    HARD_FILTERS_FORMULA_ID,
    HARD_FILTERS_SEMANTIC_CONTRACT_ID,
    MISSING_ACTION_PASS_WITHOUT_EVALUATION,
    MISSING_ACTION_PROPAGATE_PROVIDER_ERROR,
    MISSING_ACTION_RAISE_CONTRACT_ERROR,
    MISSING_ACTION_REJECTED_FLOW,
    MISSING_ACTION_REJECTED_SIGNAL,
    build_accum_score_weights_payload,
    build_all_accumulation_policy_payloads,
    build_hard_filters_payload,
    build_raw_score_identity_payload,
)
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
    canonical_json,
)


def _default_hard_filters() -> AccumulationScreenHardFilterPolicy:
    return AccumulationScreenHardFilterPolicy(
        min_market_cap_idr=0,
        min_piotroski=0,
        min_accum_score=0.0,
        min_accum_score_enabled=True,
        min_signal_score=45.0,
        min_signal_score_enabled=False,
    )


def test_closed_set_payloads_are_byte_stable() -> None:
    hard = _default_hard_filters()
    payloads = build_all_accumulation_policy_payloads(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=hard,
    )
    assert set(payloads) == set(ACCUMULATION_PRODUCTION_POLICY_IDS)
    assert len(payloads) == 7
    again = build_all_accumulation_policy_payloads(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=hard,
    )
    for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS:
        assert canonical_json(payloads[policy_id]) == canonical_json(again[policy_id])


def test_accum_score_payload_excludes_sector_breadth() -> None:
    payload = build_accum_score_weights_payload(AccumScorePolicy())
    assert payload["policy_id"] == PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS
    assert payload["semantic_engine_contract_id"] == ACCUM_SCORE_SEMANTIC_CONTRACT_ID
    keys = {c["key"] for c in payload["components"]}
    assert "sector_breadth" not in keys
    assert any(x["key"] == "sector_breadth" for x in payload["explicitly_excluded"])


def test_raw_score_identity_points_at_producer_field() -> None:
    payload = build_raw_score_identity_payload()
    assert payload["policy_id"] == PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE
    assert payload["identity_only"] is True
    assert payload["formula_id"] is None
    assert "raw_exact_score" in payload["observation_result_fields"]["raw_exact_score"]


def test_hard_filters_payload_matches_typed_default_policy() -> None:
    policy = _default_hard_filters()
    payload = build_hard_filters_payload(policy)
    assert payload["policy_id"] == PRODUCTION_POLICY_ID_HARD_FILTERS
    assert payload["decision_type"] == "gate"
    assert payload["semantic_engine_contract_id"] == HARD_FILTERS_SEMANTIC_CONTRACT_ID
    assert payload["formula_id"] == HARD_FILTERS_FORMULA_ID
    assert payload["first_match_order"] == [
        "market_cap",
        "piotroski",
        "accum_score",
        "signal_score",
    ]
    assert payload["filters"]["market_cap"]["enabled"] is False
    assert payload["filters"]["market_cap"]["floor_idr"] == 0
    assert payload["filters"]["market_cap"]["missing_action"] == MISSING_ACTION_REJECTED_FLOW
    assert (
        payload["filters"]["market_cap"]["provider_unavailable_action"]
        == MISSING_ACTION_PASS_WITHOUT_EVALUATION
    )
    assert (
        payload["filters"]["market_cap"]["provider_exception_action"]
        == MISSING_ACTION_PROPAGATE_PROVIDER_ERROR
    )
    assert payload["filters"]["piotroski"]["enabled"] is False
    assert payload["filters"]["piotroski"]["floor"] == 0
    assert payload["filters"]["accum_score"]["enabled"] is True
    assert payload["filters"]["accum_score"]["floor"] == 0.0
    assert (
        payload["filters"]["accum_score"]["missing_action"] == MISSING_ACTION_RAISE_CONTRACT_ERROR
    )
    assert payload["filters"]["signal_score"]["enabled"] is False
    assert payload["filters"]["signal_score"]["floor"] == 45.0
    assert payload["filters"]["signal_score"]["missing_action"] == MISSING_ACTION_REJECTED_SIGNAL
    assert payload["explicitly_excluded"] == ["min_net_buy_days"]
    assert "min_net_buy_days" not in payload["filters"]


def test_hard_filters_enabled_from_floors_and_flags() -> None:
    policy = AccumulationScreenHardFilterPolicy(
        min_market_cap_idr=500_000_000_000,
        min_piotroski=5,
        min_accum_score=58.3,
        min_accum_score_enabled=True,
        min_signal_score=45.0,
        min_signal_score_enabled=True,
    )
    payload = build_hard_filters_payload(policy)
    assert payload["filters"]["market_cap"]["enabled"] is True
    assert payload["filters"]["piotroski"]["enabled"] is True
    assert payload["filters"]["accum_score"]["enabled"] is True
    assert payload["filters"]["signal_score"]["enabled"] is True
