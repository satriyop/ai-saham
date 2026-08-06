"""Setup readiness honesty: family set ⇒ readiness non-None (UNAVAILABLE ok)."""

from __future__ import annotations

from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.domain.value_objects.setup_phase_readiness import SetupReadinessStatus


def test_family_none_returns_none_flow_only():
    result = SetupPhaseReadinessEvaluator().evaluate(
        setup_family=None,
        setup_phase=None,
    )
    assert result is None


def test_family_set_returns_unavailable_not_none():
    result = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="pullback",
        setup_phase=None,
    )
    assert result is not None
    assert result.status == SetupReadinessStatus.UNAVAILABLE
    # ADR-067 §4: the reason is prose, never the name of a code symbol.
    assert result.missing_required_inputs == ("setup match not evaluated",)
    # Never invent READY — the accum path has no producer for it at all.
    assert result.status is not SetupReadinessStatus.READY
