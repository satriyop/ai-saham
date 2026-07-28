"""Setup readiness honesty: family set ⇒ readiness non-None (UNAVAILABLE ok)."""

from __future__ import annotations

from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.domain.value_objects.setup_phase_readiness import SetupReadinessStatus


def test_family_none_returns_none_flow_only():
    result = SetupPhaseReadinessEvaluator().evaluate(
        setup_family=None,
        setup_evidence=None,
        setup_phase=None,
    )
    assert result is None


def test_family_set_missing_evidence_returns_unavailable_not_none():
    result = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="pullback",
        setup_evidence=None,
        setup_phase=None,
    )
    assert result is not None
    assert result.status == SetupReadinessStatus.UNAVAILABLE
    assert "setup_evidence" in result.missing_required_inputs
    # Never invent READY without evidence
    assert result.status is not SetupReadinessStatus.READY
