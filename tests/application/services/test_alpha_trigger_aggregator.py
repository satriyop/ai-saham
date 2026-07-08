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


def _breakout_phase() -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=0.8,
        coverage_score=0.8,
        conviction_score=0.8,
        sequence_valid=True,
    )


def _flow() -> FlowConfirmationEvidence:
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
        confirmation_status="CONFIRMED",
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
