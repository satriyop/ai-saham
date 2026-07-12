"""Signal, alpha/trigger, and strategy evidence fingerprint serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.strategy_evidence import StrategyEvidence


def _alpha_trigger_fingerprint(signal: "AssessSignalResponse | None") -> dict:
    score = signal.alpha_trigger_score if signal is not None else None
    if score is None:
        return {
            "alpha_score": None,
            "trigger_score": None,
            "alpha_trigger_final_exact_score": None,
            "alpha_trigger_horizon": None,
            "alpha_trigger_alpha_weight": None,
            "flow_trigger_allowed": None,
            "alpha_trigger_route_metadata": None,
            "alpha_trigger_unavailable_reasons": [],
        }
    return {
        "alpha_score": score.alpha_score,
        "trigger_score": score.trigger_score,
        "alpha_trigger_final_exact_score": score.final_exact_score,
        "alpha_trigger_horizon": score.horizon,
        "alpha_trigger_alpha_weight": score.alpha_weight,
        "flow_trigger_allowed": score.flow_trigger_allowed,
        "alpha_trigger_route_metadata": [
            contribution.to_dict()
            for contribution in score.group_contributions
        ],
        "alpha_trigger_unavailable_reasons": list(score.unavailable_reasons),
    }


def _strategy_evidence_fingerprint(
    strategy_evidence: "StrategyEvidence | None",
) -> dict:
    if strategy_evidence is None:
        return {
            "strategy_name": None,
            "strategy_rule_name": None,
            "strategy_rule_outcome": None,
            "strategy_evidence_route": None,
            "strategy_evidence_outcome": None,
            "strategy_coverage_score": None,
            "strategy_conviction_score": None,
            "strategy_freshness_score": None,
            "strategy_rationale": [],
        }
    matched = strategy_evidence.matched_rule
    return {
        "strategy_name": strategy_evidence.strategy_name,
        "strategy_rule_name": matched.rule_name if matched else None,
        "strategy_rule_outcome": matched.rule_outcome if matched else None,
        "strategy_evidence_route": matched.evidence_route if matched else None,
        "strategy_evidence_outcome": strategy_evidence.outcome.value,
        "strategy_coverage_score": strategy_evidence.coverage_score,
        "strategy_conviction_score": strategy_evidence.conviction_score,
        "strategy_freshness_score": strategy_evidence.freshness_score,
        "strategy_rationale": list(strategy_evidence.rationale),
    }


def _candidate_observation_coverage_score(
    *,
    flow_ev: "FlowConfirmationEvidence | None",
) -> float:
    present_groups = 1 if flow_ev is not None else 0
    return round(present_groups / 2.0, 4)
