"""Focused payload contract tests for accumulation policy snapshots."""

from __future__ import annotations

from src.application.services.accumulation_policy_snapshot_payloads import (
    ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    build_accum_score_weights_payload,
    build_all_accumulation_policy_payloads,
    build_raw_score_identity_payload,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
    canonical_json,
)


def test_closed_set_payloads_are_byte_stable() -> None:
    payloads = build_all_accumulation_policy_payloads(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
    )
    assert set(payloads) == set(ACCUMULATION_PRODUCTION_POLICY_IDS)
    again = build_all_accumulation_policy_payloads(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
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
