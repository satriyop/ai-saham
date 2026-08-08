"""Typed accumulation structural-filter decision contract."""

import pytest

from src.application.dto.accumulation_structural_filter import (
    StructuralFilterDecision,
    StructuralFilterField,
    StructuralFilterRejectionReason,
)


def test_rejected_decision_round_trips_exactly() -> None:
    decision = StructuralFilterDecision.rejected(
        field=StructuralFilterField.MARKET_CAP_IDR,
        reason=StructuralFilterRejectionReason.BELOW_THRESHOLD,
        observed_value=50,
        threshold=100,
    )

    assert StructuralFilterDecision.from_mapping(decision.to_dict()) == decision


@pytest.mark.parametrize(
    "mutation",
    (
        {"extra": "field"},
        {"outcome": "unknown"},
        {"threshold": True},
        {"reason": "missing_value", "observed_value": 50},
        {"reason": "below_threshold", "observed_value": None},
    ),
)
def test_invalid_persisted_decision_fails_closed(mutation: dict) -> None:
    payload = StructuralFilterDecision.rejected(
        field=StructuralFilterField.PIOTROSKI_F_SCORE,
        reason=StructuralFilterRejectionReason.BELOW_THRESHOLD,
        observed_value=3,
        threshold=5,
    ).to_dict()
    payload.update(mutation)

    with pytest.raises(ValueError):
        StructuralFilterDecision.from_mapping(payload)


@pytest.mark.parametrize(
    ("observed_value", "threshold"),
    [(100, 100), (101, 100), (True, 100), (99, False), (99, 0)],
)
def test_below_threshold_decision_rejects_semantically_invalid_numbers(
    observed_value: object,
    threshold: object,
) -> None:
    with pytest.raises(ValueError):
        StructuralFilterDecision.rejected(
            field=StructuralFilterField.MARKET_CAP_IDR,
            reason=StructuralFilterRejectionReason.BELOW_THRESHOLD,
            observed_value=observed_value,  # type: ignore[arg-type]
            threshold=threshold,  # type: ignore[arg-type]
        )
