from src.application.services.decision_policy import DecisionPolicyService
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import (
    SetupPhaseReadiness,
    SetupReadinessStatus,
)
from src.domain.value_objects.signal_assessment import EntryQuality


def _readiness(
    status: SetupReadinessStatus,
    *,
    current_phase: SetupPhaseState | None = SetupPhaseState.BREAKOUT_CONFIRMATION,
    failed_requirements: tuple[str, ...] = (),
    missing_required_inputs: tuple[str, ...] = (),
) -> SetupPhaseReadiness:
    return SetupPhaseReadiness(
        setup_family="foreign_bounce",
        status=status,
        current_phase=current_phase,
        failed_requirements=failed_requirements,
        missing_required_inputs=missing_required_inputs,
    )


def test_ready_setup_readiness_applies_no_cap():
    """HIGH-2: DecisionPolicyService consumes typed SetupPhaseReadiness only —
    it structurally cannot parse setup_phase reason strings (no such
    parameter exists), unlike the removed legacy rs_policy_warning/hard_exclude
    reason-string path this replaces."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        signal_authority_coverage=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_readiness=_readiness(SetupReadinessStatus.READY),
    )

    assert result.entry_quality == EntryQuality.ENTER
    assert result.constraints.max_decision == "ENTER"


def test_ordinary_ineligible_readiness_caps_enter_to_watch():
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        signal_authority_coverage=1.0,
        market_context=None,
        setup_family="pullback-continuation",
        setup_readiness=_readiness(
            SetupReadinessStatus.INELIGIBLE,
            current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
            failed_requirements=("sequence_invalid",),
        ),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert "caps ENTER to WATCH" in result.constraints.constraint_reasons[-1]


def test_distribution_and_failed_ineligible_readiness_caps_to_avoid():
    for phase in (SetupPhaseState.DISTRIBUTION, SetupPhaseState.FAILED):
        result = DecisionPolicyService().resolve(
            entry_quality=EntryQuality.ENTER,
            score=90,
            signal_authority_coverage=1.0,
            market_context=None,
            setup_family="foreign-bounce",
            setup_readiness=_readiness(
                SetupReadinessStatus.INELIGIBLE,
                current_phase=phase,
                failed_requirements=(f"phase:{phase.value}",),
            ),
        )

        assert result.entry_quality == EntryQuality.AVOID
        assert result.constraints.max_decision == "AVOID"


def test_exhaustion_ineligible_readiness_caps_enter_to_watch():
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        signal_authority_coverage=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_readiness=_readiness(
            SetupReadinessStatus.INELIGIBLE,
            current_phase=SetupPhaseState.EXHAUSTION,
            failed_requirements=("phase:EXHAUSTION",),
        ),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"


def test_incomplete_and_unavailable_readiness_cap_enter_to_watch():
    for status, kwargs in (
        (SetupReadinessStatus.INCOMPLETE, {"failed_requirements": ("setup_match:PARTIAL",)}),
        (SetupReadinessStatus.UNAVAILABLE, {"missing_required_inputs": ("setup_evidence",)}),
    ):
        result = DecisionPolicyService().resolve(
            entry_quality=EntryQuality.ENTER,
            score=90,
            signal_authority_coverage=1.0,
            market_context=None,
            setup_family="foreign-bounce",
            setup_readiness=_readiness(status, current_phase=None, **kwargs),
        )

        assert result.entry_quality == EntryQuality.WATCH
        assert result.constraints.max_decision == "WATCH"
