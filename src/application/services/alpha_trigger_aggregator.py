"""Alpha/Trigger projection aggregator for SignalEngine evidence groups.

Layer: Application
Depends on: domain value objects only. No IO, providers, repositories, or CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerGroupContribution,
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
    EvidenceRegistration,
)

if TYPE_CHECKING:
    from src.application.services.signal_engine_config import AlphaTriggerConfig
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot


@dataclass(frozen=True)
class AlphaTriggerGroupInput:
    group: str
    score: float
    configured_weight: float
    present: bool


@dataclass(frozen=True)
class AlphaTriggerAggregationRequest:
    horizon: str
    groups: tuple[AlphaTriggerGroupInput, ...]
    setup_phase: "SetupPhaseSnapshot | None" = None
    flow_confirmation_evidence: "FlowConfirmationEvidence | None" = None


class AlphaTriggerAggregator:
    """Project canonical evidence-group scores into Alpha and Trigger views.

    Trigger score is phase-gated. Institutional-flow trigger contribution is
    routed only when setup phase is BREAKOUT_CONFIRMATION and flow confirmation
    status is CONFIRMED. Otherwise the flow score remains visible as evidence,
    but trigger contribution is blocked with an explicit reason.
    """

    def __init__(self, config: "AlphaTriggerConfig") -> None:
        self._config = config

    def aggregate(
        self,
        request: AlphaTriggerAggregationRequest,
    ) -> AlphaTriggerScore:
        horizon = request.horizon if request.horizon in self._config.route_fractions else "SWING_10D"
        route_cfg = self._config.route_fractions[horizon]
        alpha_weight = self._config.horizon_alpha_weights.get(horizon, 0.40)
        flow_trigger_allowed, flow_gate_reasons = _flow_trigger_gate(
            request.setup_phase,
            request.flow_confirmation_evidence,
        )

        contributions: list[AlphaTriggerGroupContribution] = []
        unavailable: list[str] = []
        reasons: list[str] = []
        alpha_num = 0.0
        alpha_den = 0.0
        trigger_num = 0.0
        trigger_den = 0.0
        configured_required_weight = 0.0
        configured_available_weight = 0.0
        effective_present_weight = 0.0
        inputs_by_group = {group.group: group for group in request.groups}

        for group_name, alpha_fraction in route_cfg.items():
            group_input = inputs_by_group.get(group_name)
            configured_weight = (
                max(0.0, group_input.configured_weight)
                if group_input is not None else 0.0
            )
            configured_required_weight += configured_weight

            if group_input is None or not group_input.present:
                unavailable.append(f"{group_name}:missing")
                contributions.append(
                    AlphaTriggerGroupContribution(
                        group=group_name,
                        score=0.0,
                        configured_weight=configured_weight,
                        effective_weight=0.0,
                        alpha_fraction=alpha_fraction,
                        trigger_fraction=1.0 - alpha_fraction,
                        alpha_weighted=0.0,
                        trigger_weighted=0.0,
                        evidence_status=self._registration_for(group_name).status,
                        present=False,
                        trigger_allowed=(
                            group_name != "institutional_flow" or flow_trigger_allowed
                        ),
                        reasons=("missing_evidence",),
                    )
                )
                continue

            configured_available_weight += configured_weight
            registration = self._registration_for(group_input.group)
            effective_weight = registration.effective_weight(configured_weight)
            effective_present_weight += effective_weight

            trigger_fraction = 1.0 - alpha_fraction
            trigger_allowed = True
            group_reasons: list[str] = []

            if group_input.group == "institutional_flow" and not flow_trigger_allowed:
                trigger_allowed = False
                group_reasons.extend(flow_gate_reasons)
                trigger_fraction = 0.0

            if registration.status == EvidenceAuthorityStatus.DIAGNOSTIC:
                group_reasons.append("diagnostic_report_only")
            elif registration.status == EvidenceAuthorityStatus.LOW_WEIGHT:
                group_reasons.append("low_weight_status_cap_applied")

            alpha_routed_weight = effective_weight * alpha_fraction
            trigger_routed_weight = effective_weight * trigger_fraction
            alpha_weighted = group_input.score * alpha_routed_weight
            trigger_weighted = group_input.score * trigger_routed_weight
            alpha_num += alpha_weighted
            alpha_den += alpha_routed_weight
            trigger_num += trigger_weighted
            trigger_den += trigger_routed_weight

            contributions.append(
                AlphaTriggerGroupContribution(
                    group=group_input.group,
                    score=group_input.score,
                    configured_weight=configured_weight,
                    effective_weight=effective_weight,
                    alpha_fraction=alpha_fraction,
                    trigger_fraction=1.0 - alpha_fraction,
                    alpha_weighted=alpha_weighted,
                    trigger_weighted=trigger_weighted,
                    evidence_status=registration.status,
                    present=group_input.present,
                    trigger_allowed=trigger_allowed,
                    reasons=tuple(group_reasons),
                )
            )

        alpha_score = alpha_num / alpha_den if alpha_den > 0 else None
        trigger_score = trigger_num / trigger_den if trigger_den > 0 else None
        final_exact = _blend(alpha_score, trigger_score, alpha_weight)
        if alpha_score is None:
            unavailable.append("alpha:no_production_weight")
        if trigger_score is None:
            unavailable.append("trigger:no_production_weight")
        if flow_trigger_allowed:
            reasons.append("flow_trigger_allowed_by_price_volume_confirmation")
        else:
            reasons.extend(flow_gate_reasons)

        coverage = (
            min(1.0, configured_available_weight / configured_required_weight)
            if configured_required_weight > 0 else 0.0
        )
        authority_coverage = (
            min(1.0, effective_present_weight / configured_required_weight)
            if configured_required_weight > 0 else 0.0
        )
        conviction = (final_exact / 100.0) if final_exact is not None else 0.0

        return AlphaTriggerScore(
            alpha_score=alpha_score,
            trigger_score=trigger_score,
            final_exact_score=final_exact,
            horizon=horizon,
            alpha_weight=alpha_weight,
            group_contributions=tuple(contributions),
            coverage=round(coverage, 4),
            authority_coverage=round(authority_coverage, 4),
            conviction=round(conviction, 4),
            flow_trigger_allowed=flow_trigger_allowed,
            reasons=tuple(dict.fromkeys(reasons)),
            unavailable_reasons=tuple(dict.fromkeys(unavailable)),
        )

    def _registration_for(self, group: str) -> EvidenceRegistration:
        raw = self._config.evidence_registrations.get(group)
        if raw is not None:
            return raw
        return EvidenceRegistration(
            evidence_name=group,
            status=EvidenceAuthorityStatus.DIAGNOSTIC,
            low_weight_cap=self._config.low_weight_cap,
        )


def _blend(
    alpha_score: float | None,
    trigger_score: float | None,
    alpha_weight: float,
) -> float | None:
    if alpha_score is None and trigger_score is None:
        return None
    if alpha_score is None:
        return trigger_score
    if trigger_score is None:
        return alpha_score
    return (alpha_weight * alpha_score) + ((1.0 - alpha_weight) * trigger_score)


def _flow_trigger_gate(
    setup_phase: "SetupPhaseSnapshot | None",
    flow_confirmation_evidence: "FlowConfirmationEvidence | None",
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if setup_phase is None:
        reasons.append("flow_trigger_blocked:no_setup_phase")
    elif setup_phase.current_phase.value != "BREAKOUT_CONFIRMATION":
        reasons.append(
            "flow_trigger_blocked:setup_phase_not_breakout_confirmation"
        )
    if flow_confirmation_evidence is None:
        reasons.append("flow_trigger_blocked:no_flow_confirmation_evidence")
    elif flow_confirmation_evidence.confirmation_status != "CONFIRMED":
        reasons.append("flow_trigger_blocked:flow_not_confirmed")
    return (not reasons), tuple(reasons)
