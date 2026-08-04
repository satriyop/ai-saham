"""Legacy labeled_at digest classification and modern rehash."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest

from src.domain.value_objects.learning_artifacts import (
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningOutcomeLabel,
    OutcomeBasis,
    artifact_digest,
    label_has_legacy_labeled_at_digest,
    legacy_labeled_at_label_digest,
    modern_label_digest,
    rehash_label_excluding_labeled_at,
    validate_artifact_integrity,
)

NOW = datetime(2026, 7, 29, 11, 12, 23, 553620, tzinfo=timezone.utc)


def _modern_label() -> LearningOutcomeLabel:
    return LearningOutcomeLabel.create(
        contract_id=LearningContractId.PRE_OPEN_LABEL,
        observation_id="obs-pad-1",
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="FAILURE",
        metrics={"open_to_close_return_pct": -1.3333, "ticker": "PADI"},
        fingerprint="fp-1",
        labeled_at=NOW,
    )


def _legacy_label() -> LearningOutcomeLabel:
    """Simulate a pre-11bfca95 row: digest includes labeled_at."""
    modern = _modern_label()
    payload = asdict(modern)
    payload.pop("label_id")
    payload.pop("artifact_digest")
    legacy_digest = artifact_digest(payload)
    assert legacy_digest == legacy_labeled_at_label_digest(modern)
    assert legacy_digest != modern.artifact_digest
    return replace(modern, artifact_digest=legacy_digest)


def test_detects_legacy_labeled_at_digest() -> None:
    legacy = _legacy_label()
    assert label_has_legacy_labeled_at_digest(legacy) is True
    assert label_has_legacy_labeled_at_digest(_modern_label()) is False


def test_rehash_upgrades_legacy_to_modern_without_touching_outcome() -> None:
    legacy = _legacy_label()
    fixed = rehash_label_excluding_labeled_at(legacy)
    assert fixed.artifact_digest == modern_label_digest(legacy)
    assert fixed.artifact_digest != legacy.artifact_digest
    assert fixed.outcome == legacy.outcome
    assert fixed.metrics == legacy.metrics
    assert fixed.fingerprint == legacy.fingerprint
    assert fixed.labeled_at == legacy.labeled_at
    assert fixed.label_id == legacy.label_id
    validate_artifact_integrity(fixed, id_field="label_id")


def test_rehash_is_noop_when_already_modern() -> None:
    modern = _modern_label()
    assert rehash_label_excluding_labeled_at(modern) is modern or (
        rehash_label_excluding_labeled_at(modern).artifact_digest == modern.artifact_digest
    )


def test_rehash_refuses_unknown_corruption() -> None:
    modern = _modern_label()
    bogus = replace(modern, artifact_digest="0" * 64)
    with pytest.raises(LearningContractError, match="neither modern nor legacy"):
        rehash_label_excluding_labeled_at(bogus)
