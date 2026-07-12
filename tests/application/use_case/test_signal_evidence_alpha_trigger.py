"""Alpha/trigger projection and setup phase/gate tests."""

import pytest

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.use_case.assess_signal_use_case import (
    DecisionPolicyConfig,
    RegimeDecisionPolicyConfig,
    SignalEngineConfig,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from tests.application.use_case.signal_evidence_fixtures import (
    _company_quality,
    _flow_evidence,
    _phase_state,
    _req,
    _sector_context,
    _setup_evidence,
    _setup_phase,
    _use_case,
)


def test_setup_phase_coverage_and_conviction_drive_decision_floors():
    config = SignalEngineConfig(
        decision_policy=DecisionPolicyConfig(
            regime_policy={
                "RISK_ON": RegimeDecisionPolicyConfig(
                    enter_allowed=True,
                    max_decision="ENTER",
                    enter_threshold=70,
                    watch_threshold=45,
                    min_coverage=0.7,
                    min_conviction=0.7,
                ),
                "NEUTRAL": RegimeDecisionPolicyConfig(),
                "RISK_OFF": RegimeDecisionPolicyConfig(enter_allowed=False, max_decision="WATCH"),
                "VOLATILE": RegimeDecisionPolicyConfig(enter_allowed=False, max_decision="WATCH"),
            }
        )
    )
    resp = _use_case(config).execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=_setup_phase(coverage=0.2, conviction=0.2),
        )
    )

    assert resp.evidence_confidence == 1.0
    assert resp.assessment.entry_quality.value == "WATCH"
    assert any(
        "ENTER requires coverage" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


def test_confirmation_only_setup_evidence_caps_enter_to_watch():
    """smart-money-confirmed MATCH with entry_authority=False must not
    independently produce ENTER, even with a high combined score."""
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence(
                "MATCH",
                setup_name="smart-money-confirmed",
                setup_family="confirmation",
                entry_authority=False,
            ),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="smart-money-confirmed",
        )
    )

    assert resp.assessment.entry_quality.value == "WATCH"
    assert resp.assessment.decision_constraints.max_decision == "WATCH"
    assert any(
        "smart_money_confirmed has no standalone entry authority" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


def test_phase_gated_setup_evidence_caps_enter_when_phase_not_breakout():
    """foreign-bounce MATCH but setup_phase=ACCUMULATION caps ENTER to WATCH."""
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence(
                "MATCH",
                setup_name="foreign-bounce",
                setup_family="accumulation",
                entry_authority=True,
                can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
            ),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=_phase_state(SetupPhaseState.ACCUMULATION),
        )
    )

    assert resp.assessment.entry_quality.value == "WATCH"
    assert resp.assessment.decision_constraints.max_decision == "WATCH"
    assert any(
        "requires phase BREAKOUT_CONFIRMATION for ENTER" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


def test_phase_gated_setup_evidence_allows_enter_at_breakout_confirmation():
    """foreign-bounce MATCH with setup_phase=BREAKOUT_CONFIRMATION can remain
    ENTER when nothing else caps the decision."""
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence(
                "MATCH",
                setup_name="foreign-bounce",
                setup_family="accumulation",
                entry_authority=True,
                can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
            ),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    assert resp.assessment.entry_quality.value == "ENTER"
    assert resp.assessment.decision_constraints.max_decision == "ENTER"


def test_missing_setup_phase_with_required_phases_caps_enter_to_watch():
    """Missing setup_phase with a phase-gated setup must not default-allow ENTER."""
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence(
                "MATCH",
                setup_name="foreign-bounce",
                setup_family="accumulation",
                entry_authority=True,
                can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
            ),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=None,
        )
    )

    assert resp.assessment.entry_quality.value == "WATCH"
    assert any(
        "requires setup phase for ENTER" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


def test_alpha_trigger_projection_uses_existing_group_scores():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.horizon == "SWING_10D"
    assert at.alpha_score == pytest.approx(50.0)
    assert at.trigger_score == pytest.approx(92.6829268293)
    assert at.final_exact_score == pytest.approx(75.6097560976)
    assert at.coverage == pytest.approx(0.65)
    assert at.authority_coverage == pytest.approx(0.65)
    assert {c.group for c in at.group_contributions} == {
        "setup_quality",
        "institutional_flow",
        "market_context",
        "company_quality_context",
    }
    assert "market_context:missing" in at.unavailable_reasons
    assert "company_quality_context:missing" in at.unavailable_reasons
    assert resp.assessment.score == 80
    assert resp.assessment.raw_exact_score == pytest.approx(80.0)
    final_score = resp.assessment.to_dict()["alpha_trigger_score"]["final_exact_score"]
    assert final_score == pytest.approx(75.6098)


def test_alpha_trigger_sector_context_feeds_market_slot_as_diagnostic_coverage():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context("BULLISH"),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.coverage == pytest.approx(0.90)
    assert at.authority_coverage == pytest.approx(0.65)
    assert at.alpha_score == pytest.approx(50.0)
    assert at.trigger_score == pytest.approx(92.6829268293)
    market = [c for c in at.group_contributions if c.group == "market_context"][0]
    assert market.present is True
    assert market.score == pytest.approx(75.0)
    assert market.effective_weight == pytest.approx(0.0)
    assert "diagnostic_report_only" in market.reasons


def test_alpha_trigger_company_quality_feeds_slot_as_diagnostic_coverage():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            company_quality_context_evidence=_company_quality(72.0),
        )
    )

    at = resp.alpha_trigger_score
    assert at is not None
    cq = [c for c in at.group_contributions if c.group == "company_quality_context"][0]
    assert cq.present is True
    assert cq.score == pytest.approx(72.0)
    assert cq.effective_weight == pytest.approx(0.0)
    assert "diagnostic_report_only" in cq.reasons
    assert cq.alpha_fraction == pytest.approx(1.0)


def test_company_quality_slot_has_zero_scoring_authority():
    """DIAGNOSTIC proof: a real company_quality score must NOT move final score."""
    common = dict(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
        setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )
    empty = _use_case().execute(_req(**common))
    filled = _use_case().execute(
        _req(
            **common,
            company_quality_context_evidence=_company_quality(88.0),
        )
    )

    assert filled.alpha_trigger_score.final_exact_score == pytest.approx(
        empty.alpha_trigger_score.final_exact_score
    )
    assert filled.alpha_trigger_score.alpha_score == pytest.approx(
        empty.alpha_trigger_score.alpha_score
    )
    assert filled.assessment.score == empty.assessment.score
    cq = [
        c
        for c in filled.alpha_trigger_score.group_contributions
        if c.group == "company_quality_context"
    ][0]
    assert cq.present is True
    assert cq.effective_weight == pytest.approx(0.0)


def test_alpha_trigger_missing_groups_do_not_neutral_fill_side_denominators():
    resp = _use_case().execute(_req(setup_evidence=_setup_evidence("MATCH")))

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.alpha_score is None
    assert at.trigger_score == pytest.approx(100.0)
    assert at.final_exact_score == pytest.approx(100.0)
    assert at.coverage == pytest.approx(0.35)
    assert at.authority_coverage == pytest.approx(0.35)
    assert "institutional_flow:missing" in at.unavailable_reasons
    assert "market_context:missing" in at.unavailable_reasons
    assert "company_quality_context:missing" in at.unavailable_reasons
    assert "alpha:no_production_weight" in at.unavailable_reasons


def test_flow_does_not_contribute_to_trigger_without_price_volume_confirmation():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.COMPRESSION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.flow_trigger_allowed is False
    assert at.alpha_score == pytest.approx(50.0)
    assert at.trigger_score == pytest.approx(100.0)
    flow = [c for c in at.group_contributions if c.group == "institutional_flow"][0]
    assert flow.trigger_allowed is False
    assert "flow_trigger_blocked:setup_phase_not_breakout_confirmation" in flow.reasons


def test_breakout_confirmation_with_confirmed_flow_unlocks_flow_trigger_contribution():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(
                capped_strength=0.50,
                confirmation_status="CONFIRMED",
            ),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.flow_trigger_allowed is True
    assert at.trigger_score == pytest.approx(92.6829268293)


def test_flow_still_blocked_when_breakout_phase_lacks_confirmed_flow():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(
                capped_strength=0.50,
                confirmation_status="WATCH_ZONE",
            ),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.flow_trigger_allowed is False
    assert at.trigger_score == pytest.approx(100.0)
    assert "flow_trigger_blocked:flow_not_confirmed" in at.reasons
    assert resp.evidence_confidence == pytest.approx(1.0)
    assert resp.coverage_warning is None


def test_diagnostic_producers_zero_authority():
    """Verify that strategy, institutional accumulation, and ticker profile diagnostic
    producers are not accepted by AssessSignalEvidenceRequest, and that sector context
    and company quality context are diagnostic-only (zero effective weight).
    """

    fields = [f.name for f in AssessSignalEvidenceRequest.__dataclass_fields__.values()]
    assert "strategy_evidence" not in fields
    assert "institutional_accumulation_evidence" not in fields
    assert "ticker_profile_snapshot" not in fields

    uc = _use_case()
    common = dict(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
        setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )
    empty = uc.execute(_req(**common))
    filled = uc.execute(
        _req(
            **common,
            sector_context_evidence=_sector_context("BULLISH"),
            company_quality_context_evidence=_company_quality(88.0),
        )
    )

    assert filled.alpha_trigger_score.final_exact_score == pytest.approx(
        empty.alpha_trigger_score.final_exact_score
    )
    assert filled.assessment.score == empty.assessment.score
    market = [
        c for c in filled.alpha_trigger_score.group_contributions if c.group == "market_context"
    ][0]
    cq = [
        c
        for c in filled.alpha_trigger_score.group_contributions
        if c.group == "company_quality_context"
    ][0]
    assert market.effective_weight == pytest.approx(0.0)
    assert cq.effective_weight == pytest.approx(0.0)
