"""
Tests for DecisionPolicyService setup entry-authority enforcement.

Confirmation-only setups (entry_authority=false) must not independently
produce ENTER, and phase-gated setups (can_enter_from_phases non-empty)
must only ENTER from an allowed setup_phase. Metadata is explicit config
input to resolve() — never inferred from setup name.
"""

from __future__ import annotations

from src.application.services.decision_policy import DecisionPolicyService
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.signal_assessment import EntryQuality


def _phase(state: SetupPhaseState) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=state,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=0.8,
        coverage_score=1.0,
        conviction_score=0.8,
        sequence_valid=True,
    )


def test_confirmation_only_setup_caps_enter_to_watch():
    """smart-money-confirmed MATCH must not independently produce ENTER."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="smart-money-confirmed",
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
        setup_entry_authority=False,
        setup_can_enter_from_phases=(),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert any(
        "smart_money_confirmed has no standalone entry authority" in r
        for r in result.constraints.constraint_reasons
    )


def test_phase_gated_setup_wrong_phase_caps_enter_to_watch():
    """foreign-bounce MATCH but setup_phase=ACCUMULATION caps ENTER to WATCH."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
        setup_entry_authority=True,
        setup_can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert any(
        "requires phase BREAKOUT_CONFIRMATION for ENTER" in r
        and "current phase ACCUMULATION" in r
        for r in result.constraints.constraint_reasons
    )


def test_phase_gated_setup_correct_phase_can_remain_enter():
    """foreign-bounce MATCH with setup_phase=BREAKOUT_CONFIRMATION stays ENTER
    when score/risk floors allow (no other cap fires)."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION),
        setup_entry_authority=True,
        setup_can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    )

    assert result.entry_quality == EntryQuality.ENTER
    assert result.constraints.max_decision == "ENTER"
    assert not any(
        "requires phase" in r or "no standalone entry authority" in r
        for r in result.constraints.constraint_reasons
    )


def test_missing_setup_phase_with_required_phases_caps_enter_to_watch():
    """Missing setup_phase with a non-empty can_enter_from_phases must not
    default-allow ENTER."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=None,
        setup_entry_authority=True,
        setup_can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert any(
        "requires setup phase for ENTER" in r
        for r in result.constraints.constraint_reasons
    )


def test_coiled_spring_breakout_family_still_respects_own_entry_authority():
    """coiled-spring's family YAML value changed from accumulation to breakout
    (ADR: sequence-validity policy moved to config), but DecisionPolicyService's
    entry-authority enforcement is independent of family/setup_family — it is
    sourced purely from the explicit setup_entry_authority /
    setup_can_enter_from_phases arguments. This must be unaffected."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="coiled-spring",
        setup_phase=_phase(SetupPhaseState.BREAKOUT_CONFIRMATION),
        setup_entry_authority=True,
        setup_can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    )

    assert result.entry_quality == EntryQuality.ENTER
    assert result.constraints.max_decision == "ENTER"

    downgraded = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="coiled-spring",
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
        setup_entry_authority=True,
        setup_can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    )

    assert downgraded.entry_quality == EntryQuality.WATCH
    assert downgraded.constraints.max_decision == "WATCH"


def test_entry_authority_defaults_do_not_change_existing_behavior():
    """Backward compat: omitting the new params (defaults True/()) must not
    cap ENTER — preserves behavior for callers that don't supply setup metadata."""
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )

    assert result.entry_quality == EntryQuality.ENTER
    assert result.constraints.max_decision == "ENTER"
