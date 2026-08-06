"""Focused payload contract tests for accumulation policy snapshots."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.accumulation_policy_snapshot_payloads import (
    ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    EVIDENCE_GROUP_BASE_SCORE_FORMULA_ID,
    HARD_FILTERS_FORMULA_ID,
    HARD_FILTERS_SEMANTIC_CONTRACT_ID,
    MISSING_ACTION_PASS_WITHOUT_EVALUATION,
    MISSING_ACTION_PROPAGATE_PROVIDER_ERROR,
    MISSING_ACTION_RAISE_CONTRACT_ERROR,
    MISSING_ACTION_REJECTED_FLOW,
    MISSING_ACTION_REJECTED_SIGNAL,
    SIGNAL_SEMANTIC_CONTRACT_ID,
    build_accum_score_weights_payload,
    build_all_accumulation_policy_payloads,
    build_evidence_group_weights_payload,
    build_hard_filters_payload,
    build_raw_score_identity_payload,
)
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScorer
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
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


def test_evidence_group_payload_declares_one_production_basis() -> None:
    """ADR-067: the payload declares exactly the surviving evidence group.

    A second component, or a component under the retired name, would mean the
    declared policy had drifted back to a two-name basis the engine no longer
    has.
    """
    groups = SignalEngineConfig().evidence_groups
    payload = build_evidence_group_weights_payload(groups)

    assert payload["policy_id"] == PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS
    assert payload["decision_type"] == "score"
    assert payload["semantic_engine_contract_id"] == SIGNAL_SEMANTIC_CONTRACT_ID
    assert payload["formula_id"] == EVIDENCE_GROUP_BASE_SCORE_FORMULA_ID

    components = payload["components"]
    assert [c["key"] for c in components] == ["flow_confirmation"]
    only = components[0]
    assert only["enabled"] is True
    assert only["weight"] == groups.flow_confirmation.weight
    assert only["authority_registration"] == groups.flow_confirmation.authority_registration
    assert only["required_for_authority"] == groups.flow_confirmation.required_for_authority

    # The neutral prior is a whole-score fallback, never a per-group fill.
    assert payload["missing_data"]["neutral_fill"] is False
    assert payload["missing_data"]["no_groups_present_base_score"] == 50.0
    # The deleted blend was the only denominator; nothing may still declare one.
    assert "missing_groups_excluded_from_denominator" not in payload["missing_data"]


def test_evidence_group_payload_declares_the_real_producer_field() -> None:
    """The declared observation field must exist on the producing response.

    Until ADR-067 slice 5 this row pointed at
    ``features_by_window.7.signal.group_contributions``, a field the screen
    path has never written — the evidence-group score is ``raw_group_score``.
    A declared field that no producer emits makes the archived policy record
    unusable for replay, so the reference is asserted against the DTO the
    observation payload serializes rather than against a copy of the string.
    """
    payload = build_evidence_group_weights_payload(SignalEngineConfig().evidence_groups)
    declared = payload["observation_result_fields"]

    assert declared == {"raw_group_score": "features_by_window.7.signal.raw_group_score"}
    produced = {f.name for f in dataclass_fields(AssessSignalResponse)}
    for path in declared.values():
        leaf = path.rsplit(".", 1)[-1]
        assert leaf in produced, f"{path} names no field of AssessSignalResponse"


def test_evidence_group_formula_id_names_a_real_scorer_method() -> None:
    """``formula_id`` is cohort-identity material, so it must not go stale.

    It encodes ``<module>.<callable>.<version>``; if the callable is renamed
    without the declaration following, an archived cohort claims to have run a
    formula that does not exist.
    """
    payload = build_evidence_group_weights_payload(SignalEngineConfig().evidence_groups)
    module, callable_name, version = payload["formula_id"].rsplit(".", 2)
    assert module == "signal_evidence_group_scorer"
    assert version == "v1"
    assert callable(getattr(SignalEvidenceGroupScorer, callable_name, None))


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
