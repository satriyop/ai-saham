import pytest

from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerGroupContribution,
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
    EvidenceRegistration,
)


def test_evidence_registration_enforces_status_caps():
    diagnostic = EvidenceRegistration("market_context", EvidenceAuthorityStatus.DIAGNOSTIC)
    low_weight = EvidenceRegistration(
        "institutional_flow",
        EvidenceAuthorityStatus.LOW_WEIGHT,
        low_weight_cap=0.10,
    )
    production = EvidenceRegistration("setup_quality", EvidenceAuthorityStatus.PRODUCTION)

    assert diagnostic.effective_weight(0.30) == 0.0
    assert low_weight.effective_weight(0.30) == 0.10
    assert production.effective_weight(0.30) == 0.30


def test_alpha_trigger_score_serializes_exact_components():
    score = AlphaTriggerScore(
        alpha_score=80.0,
        trigger_score=60.0,
        final_exact_score=68.0,
        horizon="SWING_10D",
        alpha_weight=0.40,
        group_contributions=(
            AlphaTriggerGroupContribution(
                group="setup_quality",
                score=60.0,
                configured_weight=0.60,
                effective_weight=0.60,
                alpha_fraction=0.0,
                trigger_fraction=1.0,
                alpha_weighted=0.0,
                trigger_weighted=36.0,
                evidence_status=EvidenceAuthorityStatus.PRODUCTION,
            ),
        ),
        coverage=1.0,
        conviction=0.68,
    )

    payload = score.to_dict()

    assert payload["alpha_score"] == 80.0
    assert payload["trigger_score"] == 60.0
    assert payload["final_exact_score"] == 68.0
    assert payload["group_contributions"][0]["group"] == "setup_quality"


def test_route_fraction_bounds_are_validated():
    with pytest.raises(ValueError, match="alpha_fraction"):
        AlphaTriggerGroupContribution(
            group="setup_quality",
            score=50.0,
            configured_weight=0.60,
            effective_weight=0.60,
            alpha_fraction=1.2,
            trigger_fraction=-0.2,
            alpha_weighted=0.0,
            trigger_weighted=0.0,
            evidence_status=EvidenceAuthorityStatus.PRODUCTION,
        )
