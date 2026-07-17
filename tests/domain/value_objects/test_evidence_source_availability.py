"""Tests for EvidenceSourceAvailability / AvailabilityEnforcementMode — DQ-002 Blocker 2."""

from __future__ import annotations

from datetime import date, datetime

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
    assert len(payload["assessments"]) == 1
    assert payload["assessments"][0]["source_family"] == "candles"


def test_availability_enforcement_mode_has_only_shadow_today():
    assert AvailabilityEnforcementMode.SHADOW.value == "SHADOW"
    assert list(AvailabilityEnforcementMode) == [AvailabilityEnforcementMode.SHADOW]
