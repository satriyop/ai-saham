"""Build canonical production-policy snapshot payloads for accumulation.

Layer: Application (pure). Assembles material policy descriptions from already
resolved typed engine objects — no I/O, no YAML.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.signal_engine_config import (
    EvidenceGroupsConfig,
    SignalClassificationConfig,
    SignalEngineConfig,
    SignalFlagsConfig,
)
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import RiskGate
from src.domain.value_objects.learning_artifacts import (
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    PRODUCTION_POLICY_ID_RISK_HARD_GATES,
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION,
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
    PRODUCTION_POLICY_VERSION_V1,
)

# Semantic contract identifiers embedded in snapshot rows (stable strings).
ACCUM_SCORE_SEMANTIC_CONTRACT_ID = "accum_score_policy.v1"
# Frozen since ADR-068. It used to interpolate the deleted SEMANTIC_ENGINE_VERSION
# constant; it is now a stable contract *name* like its siblings above and below,
# not a change detector. Engine behaviour changes are detected by the behavioural
# probe digest, so nothing bumps this string.
SIGNAL_SEMANTIC_CONTRACT_ID = "signal.semantic_engine.v1.5"
RISK_HARD_GATES_SEMANTIC_CONTRACT_ID = "risk.hard_gates.accum.v1"
HARD_FILTERS_SEMANTIC_CONTRACT_ID = "screen.accum.hard_filters.v1"
HARD_FILTERS_FORMULA_ID = "accumulation_screen.first_match_hard_filters.v1"

# Closed missing/action vocabulary (ADR-059 v2 / activation task).
MISSING_ACTION_PASS_WITHOUT_EVALUATION = "pass_without_evaluation"
MISSING_ACTION_REJECTED_FLOW = "rejected_flow"
MISSING_ACTION_REJECTED_SIGNAL = "rejected_signal"
MISSING_ACTION_RAISE_CONTRACT_ERROR = "raise_contract_error"
MISSING_ACTION_PROPAGATE_PROVIDER_ERROR = "propagate_provider_error"

# Canonical observation window used by accumulation session capture.
ACCUM_CANONICAL_WINDOW = 7

RAW_EXACT_SCORE_FIELD = f"features_by_window.{ACCUM_CANONICAL_WINDOW}.signal.raw_exact_score"
ASSESSMENT_SCORE_FIELD = f"features_by_window.{ACCUM_CANONICAL_WINDOW}.signal.assessment.score"


def _component(
    key: str,
    *,
    enabled: bool,
    weight: float | None = None,
    **material: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {"key": key, "enabled": enabled}
    if weight is not None:
        row["weight"] = weight
    row.update(material)
    return row


def build_accum_score_weights_payload(policy: AccumScorePolicy) -> dict[str, Any]:
    """Material AccumScorePolicy / BCI components only (no sector breadth)."""

    return {
        "policy_id": PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "score",
        "semantic_engine_contract_id": ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
        "formula_id": "score_accum_use_case.v1",
        "output_scale": {"min": 0.0, "max": policy.max_score},
        "max_score": policy.max_score,
        "missing_data": {
            "optional_component_status": "MISSING",
            "missing_contributes_points": False,
            "neutral_fill": False,
        },
        "components": [
            _component(
                "consistency",
                enabled=policy.consistency.enabled,
                weight=policy.consistency.weight,
            ),
            _component(
                "streak",
                enabled=policy.streak.enabled,
                weight=policy.streak.weight,
                tau_days=policy.streak.tau_days,
            ),
            _component(
                "vwap_discount",
                enabled=policy.vwap_discount.enabled,
                weight=policy.vwap_discount.weight,
                saturate_at=policy.vwap_discount.saturate_at,
            ),
            _component(
                "rsi_headroom",
                enabled=policy.rsi_headroom.enabled,
                weight=policy.rsi_headroom.weight,
                low=policy.rsi_headroom.low,
                peak=policy.rsi_headroom.peak,
                high=policy.rsi_headroom.high,
            ),
            _component(
                "foreign_flow_ratio",
                enabled=policy.foreign_flow_ratio.enabled,
                weight=policy.foreign_flow_ratio.weight,
                saturate_at=policy.foreign_flow_ratio.saturate_at,
            ),
            _component(
                "bb_squeeze",
                enabled=policy.bb_squeeze.enabled,
                weight=policy.bb_squeeze.weight,
                tight_pctile=policy.bb_squeeze.tight_pctile,
                loose_pctile=policy.bb_squeeze.loose_pctile,
            ),
            _component(
                "bci",
                enabled=policy.bci.enabled,
                weight=None,
                cluster_points=policy.bci.cluster_points,
                stable_points=policy.bci.stable_points,
            ),
        ],
        "explicitly_excluded": [
            {
                "key": "sector_breadth",
                "reason": (
                    "Retired from production policy by ADR-062; never part of "
                    "the production accumulation baseline."
                ),
            }
        ],
        "observation_result_fields": {
            "accum_score": (f"features_by_window.{ACCUM_CANONICAL_WINDOW}.accum.score_points"),
        },
    }


def build_evidence_group_weights_payload(groups: EvidenceGroupsConfig) -> dict[str, Any]:
    return {
        "policy_id": PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "score",
        "semantic_engine_contract_id": SIGNAL_SEMANTIC_CONTRACT_ID,
        "formula_id": "signal_evidence_group_scorer.renormalize.v1",
        "output_scale": {"min": 0.0, "max": 100.0},
        "missing_data": {
            "missing_groups_excluded_from_denominator": True,
            "neutral_fill": False,
            "no_groups_present_base_score": 50.0,
        },
        "components": [
            _component(
                "flow_confirmation",
                enabled=True,
                weight=groups.flow_confirmation.weight,
                authority_registration=groups.flow_confirmation.authority_registration,
                required_for_authority=groups.flow_confirmation.required_for_authority,
            ),
        ],
        "observation_result_fields": {
            "group_contributions": (
                f"features_by_window.{ACCUM_CANONICAL_WINDOW}.signal.group_contributions"
            ),
        },
    }


def build_signal_flags_payload(flags: SignalFlagsConfig) -> dict[str, Any]:
    return {
        "policy_id": PRODUCTION_POLICY_ID_SIGNAL_FLAGS,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "score",
        "semantic_engine_contract_id": SIGNAL_SEMANTIC_CONTRACT_ID,
        "formula_id": "signal_evidence_group_scorer.flags.v1",
        "output_scale": {"min": 0.0, "max": 100.0},
        "missing_data": {
            "missing_context_skips_flag": True,
            "missing_applies_penalty": False,
        },
        "components": [
            _component(
                "valuation_stretched",
                enabled=flags.valuation_stretched.enabled,
                weight=float(flags.valuation_stretched.score_penalty),
                score_penalty=flags.valuation_stretched.score_penalty,
                forward_pe_threshold=flags.valuation_stretched.forward_pe_threshold,
            ),
            _component(
                "analyst_bearish",
                enabled=flags.analyst_bearish.enabled,
                weight=float(flags.analyst_bearish.score_penalty),
                score_penalty=flags.analyst_bearish.score_penalty,
                buy_ratio_threshold=flags.analyst_bearish.buy_ratio_threshold,
            ),
            _component(
                "insider_selling",
                enabled=flags.insider_selling.enabled,
                weight=float(flags.insider_selling.score_penalty),
                score_penalty=flags.insider_selling.score_penalty,
                net_buy_ratio_threshold=flags.insider_selling.net_buy_ratio_threshold,
            ),
        ],
        "observation_result_fields": {
            "flag_adjustment": (
                f"features_by_window.{ACCUM_CANONICAL_WINDOW}.signal.flag_adjustment"
            ),
            "active_flags": (f"features_by_window.{ACCUM_CANONICAL_WINDOW}.signal.active_flags"),
        },
    }


def build_signal_classification_payload(
    classification: SignalClassificationConfig,
) -> dict[str, Any]:
    return {
        "policy_id": PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "score",
        "semantic_engine_contract_id": SIGNAL_SEMANTIC_CONTRACT_ID,
        "formula_id": "signal_engine.classification.v1",
        "output_scale": {"min": 0.0, "max": 100.0},
        "thresholds": {
            "strong_min_score": classification.strong_min_score,
            "moderate_min_score": classification.moderate_min_score,
        },
        "bands": [
            {
                "key": "STRONG",
                "min_score": classification.strong_min_score,
            },
            {
                "key": "MODERATE",
                "min_score": classification.moderate_min_score,
                "max_score_exclusive": classification.strong_min_score,
            },
            {
                "key": "WEAK",
                "max_score_exclusive": classification.moderate_min_score,
            },
        ],
        "applies_to": "rounded_final_score",
        "note": (
            "Score-band classification thresholds only; not an outcome label "
            "and not DecisionPolicy Action authority."
        ),
        "observation_result_fields": {
            "assessment_score": ASSESSMENT_SCORE_FIELD,
            "raw_exact_score": RAW_EXACT_SCORE_FIELD,
        },
    }


def _serialize_gate(gate: RiskGate) -> dict[str, Any]:
    if isinstance(gate, FundamentalGate):
        policy = gate._policy  # noqa: SLF001 — typed material extraction
        return {
            "key": "fundamental_gate",
            "enabled": True,
            "order_family": "structural",
            "piotroski_min": gate._threshold,  # noqa: SLF001
            "missing_data_action": policy.missing_data_action,
            "missing_data_confidence": policy.missing_data_confidence,
            "triggered_confidence": policy.triggered_confidence,
            "pass_confidence": policy.pass_confidence,
        }
    if isinstance(gate, LiquidityGate):
        policy = gate._policy  # noqa: SLF001
        return {
            "key": "liquidity_gate",
            "enabled": True,
            "order_family": "structural",
            "market_cap_floor_idr": gate._cap_threshold,  # noqa: SLF001
            "median_tx_floor_idr": gate._liquidity_floor,  # noqa: SLF001
            "lookback_days": gate._lookback,  # noqa: SLF001
            "missing_data_action": policy.missing_data_action,
            "missing_data_confidence": policy.missing_data_confidence,
            "triggered_confidence": policy.triggered_confidence,
            "pass_confidence": policy.pass_confidence,
        }
    if isinstance(gate, FreeFloatGate):
        policy = gate._policy  # noqa: SLF001
        return {
            "key": "free_float_gate",
            "enabled": True,
            "order_family": "structural",
            "min_free_float_pct": gate._threshold,  # noqa: SLF001
            "missing_data_action": policy.missing_data_action,
            "missing_data_confidence": policy.missing_data_confidence,
            "triggered_confidence": policy.triggered_confidence,
            "pass_confidence": policy.pass_confidence,
        }
    if isinstance(gate, BandarGate):
        config = gate._config  # noqa: SLF001
        return {
            "key": "bandar_gate",
            "enabled": True,
            "order_family": "execution",
            "distribution_labels": sorted(config.distribution_labels),
            "missing_data_action": config.missing_data_action,
            "missing_data_confidence": config.missing_data_confidence,
            "triggered_confidence": config.triggered_confidence,
            "pass_confidence": config.pass_confidence,
        }
    raise TypeError(f"unsupported risk gate type for snapshot: {type(gate).__name__}")


def build_risk_hard_gates_payload(
    structural_gates: Sequence[RiskGate],
    execution_gates: Sequence[RiskGate],
) -> dict[str, Any]:
    gates = [_serialize_gate(g) for g in structural_gates] + [
        _serialize_gate(g) for g in execution_gates
    ]
    return {
        "policy_id": PRODUCTION_POLICY_ID_RISK_HARD_GATES,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "gate",
        "semantic_engine_contract_id": RISK_HARD_GATES_SEMANTIC_CONTRACT_ID,
        "formula_id": "assess_risk_gate_evaluator.v1",
        "short_circuit": {
            "structural_first": True,
            "structural_block_status": "BLOCKED_STRUCTURAL",
            "execution_block_status": "BLOCKED_EXECUTION",
            "order": [g["key"] for g in gates],
        },
        "missing_data": {
            "per_gate_missing_data_action": True,
            "default_when_unspecified": "skip",
        },
        "components": gates,
        "observation_result_fields": {
            "blocking_gates": (
                f"features_by_window.{ACCUM_CANONICAL_WINDOW}.trade_setup.blocking_gates"
            ),
            "risk_status": (f"features_by_window.{ACCUM_CANONICAL_WINDOW}.trade_setup.risk_status"),
        },
    }


def build_raw_score_identity_payload() -> dict[str, Any]:
    """Identity-only row: points at frozen observed field, no formula rebuild."""

    return {
        "policy_id": PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "score",
        "semantic_engine_contract_id": SIGNAL_SEMANTIC_CONTRACT_ID,
        "identity_only": True,
        "formula_id": None,
        "output_scale": {"min": 0.0, "max": 100.0},
        "observation_result_fields": {
            "raw_exact_score": RAW_EXACT_SCORE_FIELD,
            "assessment_score_display_only": ASSESSMENT_SCORE_FIELD,
        },
        "note": (
            "Production baseline is the frozen observation raw_exact_score. "
            "assessment.score is the rounded display companion, not the raw baseline."
        ),
    }


def build_hard_filters_payload(
    policy: AccumulationScreenHardFilterPolicy,
) -> dict[str, Any]:
    """Canonical payload for screener.accum.hard_filters (pre-neutralization)."""

    return {
        "policy_id": PRODUCTION_POLICY_ID_HARD_FILTERS,
        "policy_version": PRODUCTION_POLICY_VERSION_V1,
        "decision_type": "gate",
        "semantic_engine_contract_id": HARD_FILTERS_SEMANTIC_CONTRACT_ID,
        "formula_id": HARD_FILTERS_FORMULA_ID,
        "scope": "canonical_default_screen_accum",
        "first_match_order": [
            "market_cap",
            "piotroski",
            "accum_score",
            "signal_score",
        ],
        "filters": {
            "market_cap": {
                "enabled": policy.market_cap_enabled,
                "floor_idr": policy.min_market_cap_idr,
                "missing_action": MISSING_ACTION_REJECTED_FLOW,
                "provider_unavailable_action": MISSING_ACTION_PASS_WITHOUT_EVALUATION,
                "provider_exception_action": MISSING_ACTION_PROPAGATE_PROVIDER_ERROR,
                "disabled_action": MISSING_ACTION_PASS_WITHOUT_EVALUATION,
            },
            "piotroski": {
                "enabled": policy.piotroski_enabled,
                "floor": policy.min_piotroski,
                "missing_action": MISSING_ACTION_REJECTED_FLOW,
                "provider_unavailable_action": MISSING_ACTION_PASS_WITHOUT_EVALUATION,
                "provider_exception_action": MISSING_ACTION_PROPAGATE_PROVIDER_ERROR,
                "disabled_action": MISSING_ACTION_PASS_WITHOUT_EVALUATION,
            },
            "accum_score": {
                "enabled": policy.min_accum_score_enabled,
                "floor": policy.min_accum_score,
                "missing_action": MISSING_ACTION_RAISE_CONTRACT_ERROR,
                "disabled_action": MISSING_ACTION_PASS_WITHOUT_EVALUATION,
            },
            "signal_score": {
                "enabled": policy.min_signal_score_enabled,
                "floor": policy.min_signal_score,
                "missing_action": MISSING_ACTION_REJECTED_SIGNAL,
                "disabled_action": MISSING_ACTION_PASS_WITHOUT_EVALUATION,
            },
        },
        "explicitly_excluded": ["min_net_buy_days"],
        "material_source": {
            "market_cap": "accumulation_screener.screener.min_market_cap_idr",
            "market_cap_typed_path": "SwingPolicyConfig.min_market_cap_idr",
            "piotroski": "canonical_default_screen_accum.min_piotroski",
            "accum_score": "accumulation_screener.filters.min_accum_score",
            "signal_score": "accumulation_screener.filters.min_signal_score",
        },
    }


def build_all_accumulation_policy_payloads(
    *,
    accum_score_policy: AccumScorePolicy,
    signal_engine_config: SignalEngineConfig,
    structural_gates: Sequence[RiskGate],
    execution_gates: Sequence[RiskGate],
    hard_filter_policy: AccumulationScreenHardFilterPolicy,
) -> Mapping[str, Mapping[str, Any]]:
    """Return mapping policy_id -> canonical payload for the closed v2 set."""

    return {
        PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS: build_accum_score_weights_payload(
            accum_score_policy
        ),
        PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS: build_evidence_group_weights_payload(
            signal_engine_config.evidence_groups
        ),
        PRODUCTION_POLICY_ID_SIGNAL_FLAGS: build_signal_flags_payload(signal_engine_config.flags),
        PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION: build_signal_classification_payload(
            signal_engine_config.classification
        ),
        PRODUCTION_POLICY_ID_RISK_HARD_GATES: build_risk_hard_gates_payload(
            structural_gates, execution_gates
        ),
        PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE: build_raw_score_identity_payload(),
        PRODUCTION_POLICY_ID_HARD_FILTERS: build_hard_filters_payload(hard_filter_policy),
    }
