"""Pure, allow-listed projection for accumulation Judge agent commentary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from src.application.dto.accumulation_agent import (
    AgentAccumulationComponentFacts,
    AgentAccumulationContext,
    AgentAccumulationFacts,
    AgentDecisionConstraintsFacts,
    AgentDecisionRationale,
    AgentFreshnessFacts,
    AgentRiskFacts,
    AgentSetupPhaseFacts,
    AgentSetupReadinessFacts,
    AgentSignalFacts,
    AgentSourceAssessmentFacts,
    AgentSourceAvailabilityFacts,
    AgentSourceDates,
    AgentTradeSetupFacts,
)
from src.application.dto.accumulation_screen import AccumulationCandidate

SCHEMA_ID = "tui_agent.accum_judge.v1"


class AgentContextUnavailableError(ValueError):
    """A full canonical candidate is not available."""


class AgentContextInvariantError(ValueError):
    """Canonical objects disagree about ticker or snapshot identity."""


def build_agent_accumulation_context(
    candidate: AccumulationCandidate,
) -> AgentAccumulationContext:
    trade = candidate.trade_setup
    response = candidate.signal_assessment
    signal = response.assessment if response is not None else None
    accum = candidate.accum_score_breakdown
    missing = tuple(
        name
        for name, value in (
            ("trade setup", trade),
            ("signal assessment", signal),
            ("accumulation score breakdown", accum),
        )
        if value is None
    )
    if missing:
        raise AgentContextUnavailableError("Full Judge context unavailable: " + ", ".join(missing))
    assert trade is not None and signal is not None and accum is not None and response is not None

    tickers = {candidate.ticker, trade.ticker, signal.ticker, accum.ticker}
    if len({value.upper() for value in tickers}) != 1:
        raise AgentContextInvariantError(f"Agent context ticker mismatch: {sorted(tickers)}")
    # Decision identity is TradeSetup + Signal + Accum on one as-of date.
    # Risk may lag (different cache as-of) on live boards — do not hard-fail the
    # whole agent turn; surface an explicit warning instead (common IDX case).
    decision_dates = {trade.snapshot_date, signal.snapshot_date, accum.snapshot_date}
    if len(decision_dates) != 1:
        raise AgentContextInvariantError(
            "Agent context decision snapshot mismatch: "
            + ", ".join(sorted(v.isoformat() for v in decision_dates))
        )
    risk = candidate.risk_assessment
    identity_warnings: list[str] = []
    if risk is not None and risk.snapshot_date != trade.snapshot_date:
        identity_warnings.append(
            "Risk snapshot "
            f"{risk.snapshot_date.isoformat()} differs from decision as-of "
            f"{trade.snapshot_date.isoformat()}; risk is shown as diagnostic only"
        )

    constraints = signal.decision_constraints
    constraint_facts = (
        AgentDecisionConstraintsFacts(
            max_decision=constraints.max_decision,
            regime=constraints.regime,
            regime_enter_allowed=constraints.regime_enter_allowed,
            regime_size_multiplier=constraints.regime_size_multiplier,
            setup_family=constraints.setup_family,
            setup_regime_action=constraints.setup_regime_action,
            effective_size_multiplier=constraints.effective_size_multiplier,
            constraint_reasons=tuple(constraints.constraint_reasons),
        )
        if constraints is not None
        else None
    )
    trade_facts = AgentTradeSetupFacts(
        snapshot_date=trade.snapshot_date,
        action=trade.action.value,
        signal_score=trade.signal_score,
        signal_score_raw=trade.signal_score_raw,
        signal_strength=trade.signal_strength.value,
        blocking_gates=tuple(trade.blocking_gates),
        regime=trade.regime.value if trade.regime else None,
        signal_multiplier=trade.signal_multiplier,
        gate_tightening=trade.gate_tightening,
        rationale=trade.rationale,
    )
    signal_facts = AgentSignalFacts(
        identity_purpose=signal.identity.purpose.value,
        policy_contract=signal.identity.policy_contract,
        ticker=signal.ticker,
        snapshot_date=signal.snapshot_date,
        score=signal.score,
        strength=signal.strength.value,
        entry_quality=signal.entry_quality.value,
        breakdown=tuple(signal.breakdown),
        rationale=tuple(signal.rationale),
        authority_coverage=signal.signal_authority_coverage,
        coverage_warning=response.coverage_warning,
        decision_constraints=constraint_facts,
        availability_enforcement=(
            response.availability_enforcement.value
            if response.availability_enforcement is not None
            else None
        ),
    )
    risk_facts = (
        AgentRiskFacts(
            snapshot_date=risk.snapshot_date,
            verdict=risk.risk_level_name,
            gate_triggered=risk.gate_triggered,
            gate_is_structural=risk.gate_is_structural,
            gate_confidence=risk.gate_confidence,
            rationale=tuple(risk.rationale),
        )
        if risk is not None
        else None
    )
    accum_facts = AgentAccumulationFacts(
        ticker=accum.ticker,
        snapshot_date=accum.snapshot_date,
        accum_score=accum.accum_score,
        max_score=accum.max_score,
        component_coverage=accum.component_coverage,
        missing_components=tuple(accum.missing_components),
        components=tuple(
            AgentAccumulationComponentFacts(
                key=item.key,
                score_points=item.score_points,
                max_points=item.max_points,
                status=item.status.value,
            )
            for item in accum.components
        ),
        net_buy_ratio=accum.net_buy_ratio,
        consecutive_streak=accum.consecutive_streak,
        vwap_discount_pct=accum.vwap_discount_pct,
        rsi=accum.rsi,
        avg_flow_ratio=accum.avg_flow_ratio,
        bb_width_pctile=accum.bb_width_pctile,
        bci_label=accum.bci_label,
        bci_tier1_count=accum.bci_tier1_count,
    )
    readiness = response.setup_readiness
    readiness_facts = (
        AgentSetupReadinessFacts(
            setup_family=readiness.setup_family,
            status=readiness.status.value,
            current_phase=readiness.current_phase.value if readiness.current_phase else None,
            missing_required_inputs=tuple(readiness.missing_required_inputs),
            failed_requirements=tuple(readiness.failed_requirements),
        )
        if readiness is not None
        else None
    )
    phase = candidate.setup_phase
    phase_facts = (
        AgentSetupPhaseFacts(
            current_phase=phase.current_phase.value,
            previous_phase=phase.previous_phase.value if phase.previous_phase else None,
            phase_age_sessions=phase.phase_age_sessions,
            detection_strength=phase.phase_detection_strength,
            input_coverage=phase.phase_input_coverage,
            sequence_valid=phase.sequence_valid,
            reasons=tuple(phase.reasons),
            unavailable_evidence_reasons=tuple(phase.unavailable_evidence_reasons),
            volume_dry_up_ratio=phase.volume_dry_up_ratio,
            volume_expansion_ratio=phase.volume_expansion_ratio,
            volume_dry_up_confirmed=phase.volume_dry_up_confirmed,
            volume_expansion_confirmed=phase.volume_expansion_confirmed,
            volume_trigger_confirmed=phase.volume_trigger_confirmed,
        )
        if phase is not None
        else None
    )
    freshness = candidate.freshness
    freshness_facts = (
        AgentFreshnessFacts(
            candle_as_of=freshness.candle_as_of,
            broker_as_of=freshness.broker_as_of,
            expected_latest_eod=freshness.expected_latest_eod,
            candle_state=freshness.candle_state.value,
            broker_state=freshness.broker_state.value,
            alignment_state=freshness.alignment_state.value,
            sources_aligned=freshness.sources_aligned,
            signal_evidence_coverage=freshness.signal_evidence_coverage,
        )
        if freshness is not None
        else None
    )
    availability = tuple(
        _availability_facts(group)
        for group in (response.setup_source_availability, response.flow_source_availability)
        if group is not None
    )
    warnings = tuple(identity_warnings) + _warnings(response, phase, availability)
    context = AgentAccumulationContext(
        schema_id=SCHEMA_ID,
        context_reference="",
        ticker=candidate.ticker,
        as_of=trade.snapshot_date,
        trade_setup=trade_facts,
        signal=signal_facts,
        risk=risk_facts,
        accumulation=accum_facts,
        rationale=AgentDecisionRationale(
            trade_setup=trade.rationale,
            signal=tuple(signal.rationale),
            risk=tuple(risk.rationale) if risk else (),
            decision_constraints=(tuple(constraints.constraint_reasons) if constraints else ()),
            coverage_warning=response.coverage_warning,
        ),
        setup_readiness=readiness_facts,
        setup_phase_diagnostic=phase_facts,
        freshness=freshness_facts,
        source_availability=availability,
        source_dates=AgentSourceDates(
            latest_candle_date=candidate.latest_candle_date,
            latest_broker_date=candidate.latest_broker_date,
            latest_broker_daily_flow_date=candidate.latest_broker_daily_flow_date,
        ),
        warnings=warnings,
        top_brokers=tuple(candidate.top_brokers or ()),
        institutional_flag=candidate.institutional_flag,
    )
    canonical = json.dumps(
        context.canonical_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return replace(context, context_reference="sha256:" + hashlib.sha256(canonical).hexdigest())


def _availability_facts(group: object) -> AgentSourceAvailabilityFacts:
    return AgentSourceAvailabilityFacts(
        evidence_group=group.evidence_group,
        all_authoritative=group.all_authoritative,
        settled_authority_fraction=group.settled_authority_fraction,
        unassessed_contributors=tuple(group.unassessed_contributors),
        assessments=tuple(
            AgentSourceAssessmentFacts(
                source_family=item.source_family,
                decision_at=item.decision_at,
                observed_through=item.observed_through,
                available_at=item.available_at,
                expected_available_at=item.expected_available_at,
                status=item.status.value,
                is_authoritative=item.is_authoritative,
                reason=item.reason,
                notes=tuple(item.notes),
            )
            for item in group.assessments
        ),
    )


def _warnings(
    response: object,
    phase: object | None,
    groups: tuple[AgentSourceAvailabilityFacts, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    if response.coverage_warning:
        values.append(response.coverage_warning)
    if response.setup_readiness is not None:
        values.extend(response.setup_readiness.missing_required_inputs)
        values.extend(response.setup_readiness.failed_requirements)
    if phase is not None:
        values.extend(phase.unavailable_evidence_reasons)
    for group in groups:
        values.extend(group.unassessed_contributors)
        for item in group.assessments:
            if item.status != "CURRENT" or not item.is_authoritative:
                if item.reason:
                    values.append(item.reason)
                values.extend(item.notes)
    return tuple(dict.fromkeys(value for value in values if value))
