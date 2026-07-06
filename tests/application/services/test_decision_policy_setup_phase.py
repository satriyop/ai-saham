from src.application.services.decision_policy import DecisionPolicyService
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.signal_assessment import EntryQuality


def _phase(reason: str, *, sequence_valid=True) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=0.8,
        coverage_score=1.0,
        conviction_score=0.8,
        sequence_valid=sequence_valid,
        reasons=(reason,),
    )


def _terminal_phase(phase: SetupPhaseState) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=phase,
        previous_phase=None,
        phase_age_sessions=1,
        phase_strength=0.9,
        coverage_score=1.0,
        conviction_score=0.9,
        sequence_valid=None,
        reasons=(f"terminal: {phase.value}",),
    )


def test_setup_phase_rs_warning_caps_enter_to_watch():
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=_phase("rs_policy_warning: RS -2.00 <= -1.00; max_decision=WATCH"),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert any("rs_policy_warning" in r for r in result.constraints.constraint_reasons)


def test_setup_phase_rs_hard_exclude_caps_enter_to_avoid():
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=_phase("rs_policy_hard_exclude: RS -5.00 <= -4.00; max_decision=AVOID"),
    )

    assert result.entry_quality == EntryQuality.AVOID
    assert result.constraints.max_decision == "AVOID"


def test_invalid_phase_sequence_caps_enter_to_watch():
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="pullback-continuation",
        setup_phase=_phase("sequence policy", sequence_valid=False),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert "Setup phase sequence invalid" in result.constraints.constraint_reasons[-1]


def test_distribution_and_failed_terminal_phases_cap_to_avoid():
    for phase in (SetupPhaseState.DISTRIBUTION, SetupPhaseState.FAILED):
        result = DecisionPolicyService().resolve(
            entry_quality=EntryQuality.ENTER,
            score=90,
            coverage_score=1.0,
            conviction_score=1.0,
            market_context=None,
            setup_family="foreign-bounce",
            setup_phase=_terminal_phase(phase),
        )

        assert result.entry_quality == EntryQuality.AVOID
        assert result.constraints.max_decision == "AVOID"


def test_exhaustion_terminal_phase_caps_enter_to_watch():
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=_terminal_phase(SetupPhaseState.EXHAUSTION),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
