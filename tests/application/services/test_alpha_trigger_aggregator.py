from datetime import date

import pytest

from src.application.services.alpha_trigger_aggregator import (
    AlphaTriggerAggregationRequest,
    AlphaTriggerAggregator,
    AlphaTriggerGroupInput,
)
from src.application.use_case.assess_signal_use_case import AlphaTriggerConfig
from src.domain.value_objects.alpha_trigger_score import EvidenceAuthorityStatus
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState

SNAP = date(2026, 7, 3)


def test_four_group_coverage_and_diagnostic_authority_caps_are_separate():
    score = AlphaTriggerAggregator(AlphaTriggerConfig()).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput("setup_quality", 100.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 50.0, 0.30, True),
                AlphaTriggerGroupInput("market_context", 100.0, 0.25, True),
                AlphaTriggerGroupInput("company_quality_context", 0.0, 0.10, False),
            ),
            setup_phase=_breakout_phase(),
            flow_confirmation_evidence=_flow(),
        )
    )

    assert score.coverage == pytest.approx(0.90)
    assert score.authority_coverage == pytest.approx(0.65)
    assert score.alpha_score == pytest.approx(50.0)
    assert score.trigger_score == pytest.approx(92.6829268293)
    market = [c for c in score.group_contributions if c.group == "market_context"][0]
    assert market.present is True
    assert market.effective_weight == 0.0
    assert "diagnostic_report_only" in market.reasons
    assert "company_quality_context:missing" in score.unavailable_reasons


def test_market_and_company_diagnostic_groups_do_not_move_final_score():
    aggregator = AlphaTriggerAggregator(AlphaTriggerConfig())
    common = dict(
        horizon="SWING_10D",
        setup_phase=_breakout_phase(),
        flow_confirmation_evidence=_flow(),
    )
    baseline = aggregator.aggregate(
        AlphaTriggerAggregationRequest(
            **common,
            groups=(
                AlphaTriggerGroupInput("setup_quality", 100.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 50.0, 0.30, True),
            ),
        )
    )
    filled = aggregator.aggregate(
        AlphaTriggerAggregationRequest(
            **common,
            groups=(
                AlphaTriggerGroupInput("setup_quality", 100.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 50.0, 0.30, True),
                AlphaTriggerGroupInput("market_context", 100.0, 0.25, True),
                AlphaTriggerGroupInput("company_quality_context", 100.0, 0.10, True),
            ),
        )
    )

    assert filled.final_exact_score == pytest.approx(baseline.final_exact_score)
    assert filled.alpha_score == pytest.approx(baseline.alpha_score)
    assert filled.trigger_score == pytest.approx(baseline.trigger_score)
    market = [c for c in filled.group_contributions if c.group == "market_context"][0]
    company = [
        c for c in filled.group_contributions
        if c.group == "company_quality_context"
    ][0]
    assert market.effective_weight == pytest.approx(0.0)
    assert company.effective_weight == pytest.approx(0.0)
    assert market.evidence_status is EvidenceAuthorityStatus.DIAGNOSTIC
    assert company.evidence_status is EvidenceAuthorityStatus.DIAGNOSTIC


def test_flow_trigger_blocked_by_non_breakout_phase_keeps_flow_score_visible():
    score = AlphaTriggerAggregator(AlphaTriggerConfig()).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput("setup_quality", 70.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 95.0, 0.30, True),
            ),
            setup_phase=_compression_phase(),
            flow_confirmation_evidence=_flow("CONFIRMED"),
        )
    )

    flow = [c for c in score.group_contributions if c.group == "institutional_flow"][0]
    assert flow.score == pytest.approx(95.0)
    assert flow.trigger_allowed is False
    assert flow.trigger_weighted == pytest.approx(0.0)
    assert "flow_trigger_blocked:setup_phase_not_breakout_confirmation" in flow.reasons


def test_flow_trigger_routed_for_breakout_phase_with_confirmed_flow():
    score = AlphaTriggerAggregator(AlphaTriggerConfig()).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput("setup_quality", 70.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 95.0, 0.30, True),
            ),
            setup_phase=_breakout_phase(),
            flow_confirmation_evidence=_flow("CONFIRMED"),
        )
    )

    flow = [c for c in score.group_contributions if c.group == "institutional_flow"][0]
    assert flow.trigger_allowed is True
    assert flow.trigger_fraction == pytest.approx(0.20)
    assert flow.trigger_weighted == pytest.approx(5.7)
    assert not [r for r in flow.reasons if r.startswith("flow_trigger_blocked:")]
    # Canonical FlowConfirmationEvidence authority was not demoted by this task.
    assert flow.evidence_status is EvidenceAuthorityStatus.PRODUCTION
    assert flow.effective_weight == pytest.approx(0.30)


def test_fabricated_producer_status_cannot_override_central_authority():
    """A serialized/fabricated producer-local evidence_status claim must not
    grant Alpha/Trigger scoring authority; only the central
    AlphaTriggerConfig.evidence_registrations registry decides authority.

    First proves the aggregation contract has no channel to accept a
    producer-supplied status at all (AlphaTriggerGroupInput has no
    evidence_status field and rejects it if injected), then proves that with
    a central DIAGNOSTIC registration, the contribution carries zero
    authority regardless of the score value a fabricated producer claims.
    """
    from dataclasses import fields, replace

    from src.domain.value_objects.alpha_trigger_score import EvidenceRegistration

    assert "evidence_status" not in {
        field.name for field in fields(AlphaTriggerGroupInput)
    }
    with pytest.raises(TypeError):
        AlphaTriggerGroupInput(
            "institutional_flow",
            100.0,
            0.30,
            True,
            evidence_status="PRODUCTION",  # type: ignore[call-arg]
        )

    base_config = AlphaTriggerConfig()
    diagnostic_registrations = dict(base_config.evidence_registrations)
    diagnostic_registrations["institutional_flow"] = EvidenceRegistration(
        evidence_name="institutional_flow",
        status=EvidenceAuthorityStatus.DIAGNOSTIC,
    )
    config = replace(base_config, evidence_registrations=diagnostic_registrations)

    score = AlphaTriggerAggregator(config).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput("setup_quality", 70.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 100.0, 0.30, True),
            ),
            setup_phase=_breakout_phase(),
            flow_confirmation_evidence=_flow("CONFIRMED"),
        )
    )

    flow = [c for c in score.group_contributions if c.group == "institutional_flow"][0]
    assert flow.evidence_status is EvidenceAuthorityStatus.DIAGNOSTIC
    assert flow.effective_weight == 0.0
    assert "diagnostic_report_only" in flow.reasons


def test_flow_trigger_blocked_when_setup_phase_missing():
    score = AlphaTriggerAggregator(AlphaTriggerConfig()).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput("setup_quality", 70.0, 0.35, True),
                AlphaTriggerGroupInput("institutional_flow", 95.0, 0.30, True),
            ),
            setup_phase=None,
            flow_confirmation_evidence=_flow("CONFIRMED"),
        )
    )

    flow = [c for c in score.group_contributions if c.group == "institutional_flow"][0]
    assert flow.trigger_allowed is False
    assert flow.trigger_weighted == pytest.approx(0.0)
    assert "flow_trigger_blocked:no_setup_phase" in flow.reasons


def _breakout_phase() -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_detection_strength=0.8,
        phase_input_coverage=0.8,
        sequence_valid=True,
    )


def _compression_phase() -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=SetupPhaseState.COMPRESSION,
        previous_phase=SetupPhaseState.ACCUMULATION,
        phase_age_sessions=3,
        phase_detection_strength=0.8,
        phase_input_coverage=0.8,
        sequence_valid=True,
    )


def _flow(confirmation_status: str = "CONFIRMED") -> FlowConfirmationEvidence:
    signal = FlowSubSignal(
        key="cons",
        score=40.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(signal,),
        flow_score_ex_bb=40.0,
        confirmation_status=confirmation_status,
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.50,
        capped_strength=0.50,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )
