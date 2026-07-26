from datetime import date

import pytest

from src.domain.value_objects.signal_assessment import (
    ACCUMULATION_DISCOVERY_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalAssessmentIdentity,
    SignalAssessmentPurpose,
    SignalStrength,
)


def _assessment(**overrides) -> SignalAssessment:
    values = {
        "identity": ACCUMULATION_DISCOVERY_IDENTITY,
        "ticker": "BBCA",
        "score": 72,
        "strength": SignalStrength.STRONG,
        "entry_quality": EntryQuality.ENTER,
        "breakdown": (),
        "rationale": (),
        "snapshot_date": date(2026, 7, 26),
        "signal_authority_coverage": 1.0,
    }
    values.update(overrides)
    return SignalAssessment(**values)


def test_identity_serializes_with_assessment() -> None:
    assert _assessment().to_dict()["identity"] == {
        "purpose": "ACCUMULATION_DISCOVERY",
        "policy_contract": "accumulation_discovery.v1",
    }


@pytest.mark.parametrize("purpose", [None, "", "ACCUMULATION_DISCOVERY", "UNKNOWN"])
def test_identity_rejects_missing_or_unknown_purpose(purpose) -> None:
    with pytest.raises(ValueError, match="Unknown signal assessment purpose"):
        SignalAssessmentIdentity(
            purpose=purpose,
            policy_contract="accumulation_discovery.v1",
        )


@pytest.mark.parametrize("policy_contract", [None, "", "swing_trade_setup.v1", "unknown.v1"])
def test_identity_rejects_missing_unknown_or_mismatched_contract(policy_contract) -> None:
    with pytest.raises(ValueError, match="policy contract mismatch"):
        SignalAssessmentIdentity(
            purpose=SignalAssessmentPurpose.ACCUMULATION_DISCOVERY,
            policy_contract=policy_contract,
        )


def test_assessment_rejects_missing_identity() -> None:
    with pytest.raises(ValueError, match="identity is required"):
        _assessment(identity=None)
