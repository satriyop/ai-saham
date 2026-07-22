"""Tests for EvidenceSourceAvailability / AvailabilityEnforcementMode — DQ-002 Blocker 2."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.value_objects.evidence_source_availability import (
    AvailabilityEnforcementMode,
    EvidenceSourceAvailability,
)
from src.domain.value_objects.source_availability import (
    SourceAvailabilityAssessment,
    SourceAvailabilityStatus,
)

_DECISION_AT = datetime(2026, 7, 17, 20, 0, 0)


def _assessment(
    source_family: str,
    status: SourceAvailabilityStatus,
    is_authoritative: bool,
) -> SourceAvailabilityAssessment:
    return SourceAvailabilityAssessment(
        source_family=source_family,
        decision_at=_DECISION_AT,
        observed_through=date(2026, 7, 17),
        available_at=None,
        status=status,
        is_authoritative=is_authoritative,
        reason="TEST",
    )


def test_all_authoritative_true_when_every_assessment_is_authoritative():
    group = EvidenceSourceAvailability(
        evidence_group="setup",
        assessments=(
            _assessment("candles", SourceAvailabilityStatus.CURRENT, True),
        ),
    )
    assert group.all_authoritative is True


def test_all_authoritative_false_when_one_source_is_not_authoritative():
    # Two sources feed one evidence group; one is unavailable. The group must
    # not be silently treated as authoritative just because the other source
    # is current — this is the exact "do not silently mark the group
    # authoritative when one required source is unavailable" requirement.
    group = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
            _assessment("broker_daily_flow", SourceAvailabilityStatus.UNKNOWN, False),
        ),
    )
    assert group.all_authoritative is False


def test_all_authoritative_false_when_assessments_empty():
    group = EvidenceSourceAvailability(evidence_group="setup", assessments=())
    assert group.all_authoritative is False


def test_statuses_are_preserved_separately_not_averaged():
    # Regression guard: this container must not collapse two distinct
    # per-source statuses into one combined value.
    group = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
            _assessment("broker_daily_flow", SourceAvailabilityStatus.STALE, False),
        ),
    )
    statuses = [a.status for a in group.assessments]
    assert statuses == [SourceAvailabilityStatus.CURRENT, SourceAvailabilityStatus.STALE]


def test_to_dict_includes_group_and_each_assessment():
    group = EvidenceSourceAvailability(
        evidence_group="setup",
        assessments=(_assessment("candles", SourceAvailabilityStatus.CURRENT, True),),
    )
    payload = group.to_dict()
    assert payload["evidence_group"] == "setup"
    assert payload["all_authoritative"] is True
    assert payload["settled_authority_fraction"] == 1.0
    assert len(payload["assessments"]) == 1
    assert payload["assessments"][0]["source_family"] == "candles"


def test_availability_enforcement_mode_has_shadow_and_enforced():
    # HIGH-2 adds ENFORCED alongside SHADOW — authority coverage enforcement
    # is a policy change, not a new observational mode.
    assert AvailabilityEnforcementMode.SHADOW.value == "SHADOW"
    assert AvailabilityEnforcementMode.ENFORCED.value == "ENFORCED"
    assert list(AvailabilityEnforcementMode) == [
        AvailabilityEnforcementMode.SHADOW,
        AvailabilityEnforcementMode.ENFORCED,
    ]


def test_all_authoritative_false_when_a_contributor_is_unassessed():
    # Every listed assessment is authoritative, but a real, currently-present
    # contributor to this evidence group (e.g. a live-scraped sub-signal with
    # no settlement rule) was never given an assessment at all. This must not
    # be able to report all_authoritative=True — an unassessed contributor is
    # not the same as "no contributors exist to worry about".
    group = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
            _assessment("broker_daily_flow", SourceAvailabilityStatus.CURRENT, True),
        ),
        unassessed_contributors=("bandar_detector",),
    )
    assert group.all_authoritative is False
    assert group.settled_authority_fraction == 1.0


def test_settled_authority_fraction_zero_when_settled_source_not_authoritative():
    group = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
            _assessment("broker_daily_flow", SourceAvailabilityStatus.UNKNOWN, False),
        ),
        unassessed_contributors=("bandar_detector",),
    )
    assert group.all_authoritative is False
    assert group.settled_authority_fraction == 0.0


def test_all_authoritative_true_when_no_unassessed_contributors():
    group = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
            _assessment("broker_daily_flow", SourceAvailabilityStatus.CURRENT, True),
        ),
    )
    assert group.unassessed_contributors == ()
    assert group.all_authoritative is True


def test_duplicate_source_family_assessments_raise():
    with pytest.raises(ValueError, match="duplicate"):
        EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
                _assessment("broker_summaries", SourceAvailabilityStatus.STALE, False),
            ),
        )


def test_mixed_decision_at_across_assessments_raises():
    other_decision_at = datetime(2026, 7, 18, 9, 0, 0)
    mismatched = SourceAvailabilityAssessment(
        source_family="broker_daily_flow",
        decision_at=other_decision_at,
        observed_through=date(2026, 7, 17),
        available_at=None,
        status=SourceAvailabilityStatus.CURRENT,
        is_authoritative=True,
        reason="TEST",
    )
    with pytest.raises(ValueError, match="decision_at"):
        EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),
                mismatched,
            ),
        )


def test_to_dict_includes_unassessed_contributors():
    group = EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(_assessment("broker_summaries", SourceAvailabilityStatus.CURRENT, True),),
        unassessed_contributors=("bandar_detector",),
    )
    payload = group.to_dict()
    assert payload["unassessed_contributors"] == ["bandar_detector"]
    assert payload["all_authoritative"] is False
