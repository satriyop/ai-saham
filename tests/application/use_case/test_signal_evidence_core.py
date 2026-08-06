"""Core signal evidence tests for AssessSignalEvidenceUseCase."""

import pytest

from src.application.services.signal_engine_config import (
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    SignalEngineConfig,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from tests.application.use_case.signal_evidence_fixtures import (
    _flow_evidence,
    _req,
    _setup_evidence,
    _use_case,
)


def test_both_groups_missing_raises_no_production_signal_evidence_error():
    from src.application.exceptions import NoProductionSignalEvidenceError

    uc = _use_case()
    with pytest.raises(
        NoProductionSignalEvidenceError,
        match="Canonical signal assessment requires setup or flow evidence.",
    ):
        uc.execute(_req())


def test_signal_score_is_exactly_the_flow_group_score():
    """ADR-067: flow_confirmation is the sole production evidence group.

    capped_strength=0.80 → flow group score 80.0 → signal score 80. No blend,
    no renormalization, no weight divides anything. Authority coverage is
    1.0 because flow is now the only required PRODUCTION group, so a bare
    SignalEngineConfig()'s 0.70 min_signal_authority_coverage floor is met and
    DecisionPolicyService leaves the ENTER classification standing.
    """
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(capped_strength=0.80)))
    assert resp.assessment.score == 80
    assert resp.assessment.entry_quality.name == "ENTER"
    assert resp.signal_authority_coverage == pytest.approx(1.0)
    assert resp.assessment.signal_authority_coverage == pytest.approx(1.0)


def test_attached_required_flow_only_reaches_full_authority_coverage():
    from src.domain.value_objects.evidence_source_availability import (
        AuthorityDenominatorScope,
    )

    uc = _use_case()
    resp = uc.execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.80),
            authority_denominator_scope=AuthorityDenominatorScope.ATTACHED_REQUIRED,
        )
    )
    assert resp.signal_authority_coverage == pytest.approx(1.0)
    assert resp.assessment.entry_quality.name == "ENTER"


def test_settled_bandar_unassessed_does_not_zero_flow_authority():
    """Unassessed bandar blocks complete claim but settled brokers still count."""
    from src.domain.value_objects.evidence_source_availability import (
        AuthorityDenominatorScope,
    )

    uc = _use_case()
    resp = uc.execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.80),
            flow_unassessed_contributors=("bandar_detector",),
            authority_denominator_scope=AuthorityDenominatorScope.ATTACHED_REQUIRED,
        )
    )
    assert resp.signal_authority_coverage == pytest.approx(1.0)
    assert resp.flow_source_availability is not None
    assert resp.flow_source_availability.all_authoritative is False
    assert resp.flow_source_availability.settled_authority_fraction == pytest.approx(1.0)
    assert "unassessed contributors" in (resp.coverage_warning or "")


@pytest.mark.parametrize("match", ["MATCH", "PARTIAL", "NO_MATCH"])
def test_setup_evidence_alone_scores_the_neutral_prior(match):
    """ADR-067: setup evidence carries no scoring authority at any strength.

    Setup was retired as a production evidence group, so a request carrying
    only setup evidence has no production evidence present: the score is the
    explicit 50.0 neutral prior (never a neutral *fill* of a real group) and
    authority coverage is 0.0. MATCH, PARTIAL and NO_MATCH are asserted
    together because the whole point is that match strength no longer moves
    the score — a single-value test would still pass if only one branch
    regressed.
    """
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence(match)))
    assert resp.assessment.score == 50
    assert resp.signal_authority_coverage == pytest.approx(0.0)
    assert resp.assessment.entry_quality.name != "ENTER"


def test_attaching_setup_evidence_cannot_move_the_flow_score():
    """The negative form of the retirement: setup is inert beside flow.

    Before ADR-067 this blended to (100*0.60 + 50*0.40) / 1.0 = 80. Now the
    score is the flow group score, 50, regardless of setup being a full MATCH.
    """
    uc = _use_case()
    flow_only = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    with_setup = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
        )
    )
    assert with_setup.assessment.score == 50
    assert with_setup.assessment.score == flow_only.assessment.score
    assert with_setup.signal_authority_coverage == flow_only.signal_authority_coverage


def test_both_groups_present_full_strength_scores_100():
    # setup=MATCH (100) + flow capped=1.0 (100) → score=100
    uc = _use_case()
    resp = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=1.0),
        )
    )
    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.entry_quality.name == "ENTER"
    assert resp.assessment.signal_authority_coverage == pytest.approx(1.0)


@pytest.mark.parametrize("weight", [0.20, 0.40, 0.95])
def test_sole_group_weight_cannot_move_the_score_or_the_coverage(weight):
    """ADR-067 consequence, asserted so it is a decision and not a surprise.

    With one production evidence group there is nothing to weigh against it:
    ``base_score_from_flow_group`` reads no weight at all, and in the authority
    arithmetic the single group contributes ``w * fraction`` to the numerator
    and ``w`` to the denominator, so ``w`` cancels. It survives only as ADR-059
    policy-snapshot material (cohort identity), never as behaviour.

    This is the positive twin of the ``flow_confirmation.weight:x3`` equivalent
    mutant recorded in the ADR-068 mutation suite. If a second production group
    is ever registered, both should start failing together.
    """
    cfg = SignalEngineConfig(
        evidence_groups=EvidenceGroupsConfig(
            flow_confirmation=EvidenceGroupConfig(
                weight=weight,
                authority_registration="institutional_flow",
            ),
        )
    )
    resp = _use_case(cfg).execute(
        _req(flow_confirmation_evidence=_flow_evidence(capped_strength=1.0))
    )
    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.signal_authority_coverage == pytest.approx(1.0)
