"""Tests protecting SignalForwardLabel schema-aware fingerprint serialization."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalLabelHorizon,
    SignalForwardOutcome,
)
from src.domain.value_objects.signal_observation_fingerprint import (
    SignalObservationFingerprint,
)


def test_current_label_construction_rejects_removed_market_context_identity():
    """SECTOR-CONTEXT-IDENTITY (Finding 1): a current-schema label must reject
    the removed market_context Alpha/Trigger group in its fingerprint route
    metadata at construction time, before it can be persisted or feed
    readiness."""
    fp = SignalObservationFingerprint(
        alpha_trigger_route_metadata=({"group": "market_context", "score": 75.0},),
    )
    with pytest.raises(ValueError, match="removed Alpha/Trigger group 'market_context'"):
        make_label(3, fp)


def test_current_label_construction_accepts_sector_context_identity():
    fp = SignalObservationFingerprint(
        alpha_trigger_route_metadata=({"group": "sector_context", "score": 75.0},),
    )
    label = make_label(3, fp)
    assert label.fingerprint.alpha_trigger_route_metadata[0]["group"] == "sector_context"


def test_legacy_schema_1_label_construction_ignores_removed_identity():
    """Schema-1 raw labels predate the current contract and are not validated
    for group identity — they remain constructible for audit/history."""
    fp = SignalObservationFingerprint(
        alpha_trigger_route_metadata=({"group": "market_context", "score": 75.0},),
    )
    label = make_label(1, fp)
    assert label.schema_version == 1


def make_label(
    schema_version: int,
    fingerprint: SignalObservationFingerprint,
) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 12),
        close_return=5.0,
        max_forward_return=8.0,
        max_adverse_excursion=1.0,
        days_to_peak=5,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=fingerprint,
        schema_version=schema_version,
    )


def test_canonical_domain_serialization():
    # Construct a current-schema label whose fingerprint intentionally contains:
    # - all five forbidden legacy values;
    # - all canonical replacement values;
    # - representative scoped fields that must be preserved.
    fp = SignalObservationFingerprint(
        # Legacy forbidden keys
        coverage=0.5,
        conviction=0.8,
        phase_strength=0.7,
        phase_coverage_score=0.6,
        phase_conviction_score=0.4,
        # Canonical replacement keys
        signal_authority_coverage=0.75,
        setup_readiness_status="READY",
        setup_readiness_current_phase="ACCUMULATION",
        setup_readiness_missing_required_inputs=("input1",),
        setup_readiness_failed_requirements=("req1",),
        phase_detection_strength=0.85,
        phase_input_coverage=0.95,
        # Scoped metrics (must be preserved)
        ia_foreign_track_conviction=0.9,
        ia_foreign_track_coverage=0.85,
        strategy_conviction_score=0.7,
        strategy_coverage_score=0.6,
        cq_coverage_score=0.8,
    )

    label = make_label(schema_version=3, fingerprint=fp)
    payload = label.to_dict()
    fingerprint_payload = payload["fingerprint"]

    # Assert all five forbidden keys are absent.
    forbidden_keys = [
        "coverage",
        "conviction",
        "phase_strength",
        "phase_coverage_score",
        "phase_conviction_score",
    ]
    for key in forbidden_keys:
        assert key not in fingerprint_payload

    # Assert every canonical replacement key is present with its original value.
    assert fingerprint_payload["signal_authority_coverage"] == 0.75
    assert fingerprint_payload["setup_readiness_status"] == "READY"
    assert fingerprint_payload["setup_readiness_current_phase"] == "ACCUMULATION"
    assert fingerprint_payload["setup_readiness_missing_required_inputs"] == ["input1"]
    assert fingerprint_payload["setup_readiness_failed_requirements"] == ["req1"]
    assert fingerprint_payload["phase_detection_strength"] == 0.85
    assert fingerprint_payload["phase_input_coverage"] == 0.95

    # Assert representative scoped fields remain present.
    assert fingerprint_payload["ia_foreign_track_conviction"] == 0.9
    assert fingerprint_payload["ia_foreign_track_coverage"] == 0.85
    assert fingerprint_payload["strategy_conviction_score"] == 0.7
    assert fingerprint_payload["strategy_coverage_score"] == 0.6
    assert fingerprint_payload["cq_coverage_score"] == 0.8


def test_schema_1_compatibility():
    fp = SignalObservationFingerprint(
        # Legacy values
        coverage=0.5,
        conviction=0.8,
        phase_strength=0.7,
        phase_coverage_score=0.6,
        phase_conviction_score=0.4,
    )
    
    label = make_label(schema_version=1, fingerprint=fp)
    payload = label.to_dict()
    fingerprint_payload = payload["fingerprint"]
    
    # Assert label.to_dict()["fingerprint"] retains all five keys and values.
    assert fingerprint_payload["coverage"] == 0.5
    assert fingerprint_payload["conviction"] == 0.8
    assert fingerprint_payload["phase_strength"] == 0.7
    assert fingerprint_payload["phase_coverage_score"] == 0.6
    assert fingerprint_payload["phase_conviction_score"] == 0.4
    
    # Round-trip it through SignalForwardLabel.from_dict(label.to_dict())
    rt_label = SignalForwardLabel.from_dict(payload)
    
    # Assert the legacy values remain readable.
    assert rt_label.fingerprint.coverage == 0.5
    assert rt_label.fingerprint.conviction == 0.8
    assert rt_label.fingerprint.phase_strength == 0.7
    assert rt_label.fingerprint.phase_coverage_score == 0.6
    assert rt_label.fingerprint.phase_conviction_score == 0.4


def test_no_legacy_to_canonical_fabrication():
    # Construct a schema-1 payload containing only legacy coverage and phase fields.
    payload = {
        "schema_version": 1,
        "ticker": "BBCA",
        "signal_date": "2026-07-01",
        "horizon": "SWING_10D",
        "entry_reference_price": "100",
        "outcome_label": "SUCCESS",
        "fingerprint": {
            "coverage": 0.5,
            "conviction": 0.8,
            "phase_strength": 0.7,
            "phase_coverage_score": 0.6,
            "phase_conviction_score": 0.4,
        }
    }
    
    # Deserialize it.
    label = SignalForwardLabel.from_dict(payload)
    fingerprint = label.fingerprint
    
    # Assert:
    assert fingerprint.signal_authority_coverage is None
    assert fingerprint.phase_detection_strength is None
    assert fingerprint.phase_input_coverage is None
