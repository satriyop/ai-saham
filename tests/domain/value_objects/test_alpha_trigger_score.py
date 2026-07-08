import pytest

from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerGroupContribution,
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
    EvidencePromotionRecord,
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


def test_evidence_promotion_record_stores_requirements_immutably():
    record = EvidencePromotionRecord(
        target="foreign_institutional_accumulation_large_cap_SWING_10D",
        evidence_name="market_context",
        promoted_to=EvidenceAuthorityStatus.LOW_WEIGHT,
        promoted_by="manual",
        promoted_date="2026-07-08",
        attribution_ref="journals/signal-readiness/phase-i-report.json",
        requirements=(
            ("min_is_labels", 60.0),
            ("min_oos_labels", 30.0),
        ),
    )

    assert record.requirements == (
        ("min_is_labels", 60.0),
        ("min_oos_labels", 30.0),
    )
    assert record.requirements_dict == {
        "min_is_labels": 60.0,
        "min_oos_labels": 30.0,
    }
    assert record.to_dict()["requirements"] == record.requirements_dict


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


# ── canonical naming properties ───────────────────────────────────────────────

def _make_score(coverage: float = 0.75, conviction: float = 0.60,
                authority: float = 0.65) -> AlphaTriggerScore:
    return AlphaTriggerScore(
        alpha_score=70.0,
        trigger_score=55.0,
        final_exact_score=61.0,
        horizon="SWING_10D",
        alpha_weight=0.40,
        coverage=coverage,
        authority_coverage=authority,
        conviction=conviction,
    )


def test_alpha_trigger_coverage_score_property():
    ats = _make_score(coverage=0.75)
    assert ats.coverage_score == pytest.approx(0.75)
    assert ats.coverage_score == ats.coverage


def test_alpha_trigger_authority_coverage_score_property():
    ats = _make_score(authority=0.65)
    assert ats.authority_coverage_score == pytest.approx(0.65)
    assert ats.authority_coverage_score == ats.authority_coverage


def test_alpha_trigger_conviction_score_property():
    ats = _make_score(conviction=0.60)
    assert ats.conviction_score == pytest.approx(0.60)
    assert ats.conviction_score == ats.conviction


def test_alpha_trigger_to_dict_emits_canonical_and_legacy_keys():
    ats = _make_score(coverage=0.75, conviction=0.60, authority=0.65)
    d = ats.to_dict()
    # Canonical keys present
    assert "coverage_score" in d
    assert "conviction_score" in d
    assert "authority_coverage_score" in d
    # Legacy keys preserved for compatibility
    assert "coverage" in d
    assert "conviction" in d
    assert "authority_coverage" in d
    # Values agree
    assert d["coverage_score"] == pytest.approx(d["coverage"])
    assert d["conviction_score"] == pytest.approx(d["conviction"])
    assert d["authority_coverage_score"] == pytest.approx(d["authority_coverage"])
