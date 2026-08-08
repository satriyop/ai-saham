"""Typed outcome of the accumulation pre-enrichment structural filter.

Layer: Application DTO
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class StructuralFilterOutcome(str, Enum):
    """Top-level inclusion result from the structural hard filter."""

    DISABLED = "disabled"
    PASSED = "passed"
    REJECTED = "rejected"


class StructuralFilterField(str, Enum):
    """Configured field responsible for the first-match rejection."""

    MARKET_CAP_IDR = "market_cap_idr"
    PIOTROSKI_F_SCORE = "piotroski_f_score"


class StructuralFilterRejectionReason(str, Enum):
    """Why an enabled structural field rejected the candidate."""

    MISSING_VALUE = "missing_value"
    BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True)
class StructuralFilterDecision:
    """Exact first-match structural-filter result transported to persistence."""

    outcome: StructuralFilterOutcome
    field: StructuralFilterField | None = None
    reason: StructuralFilterRejectionReason | None = None
    observed_value: int | None = None
    threshold: int | None = None

    def __post_init__(self) -> None:
        rejected = self.outcome is StructuralFilterOutcome.REJECTED
        rejection_fields = (self.field, self.reason, self.threshold)
        if rejected and any(value is None for value in rejection_fields):
            raise ValueError(
                "rejected structural-filter decision requires field, reason, and threshold"
            )
        if not rejected and any(
            value is not None for value in (*rejection_fields, self.observed_value)
        ):
            raise ValueError(
                "non-rejected structural-filter decision cannot carry rejection details"
            )
        if rejected and (type(self.threshold) is not int or self.threshold <= 0):
            raise ValueError("structural rejection threshold must be a positive int")
        if self.observed_value is not None and type(self.observed_value) is not int:
            raise ValueError("structural rejection observed_value must be int or null")
        if (
            self.reason is StructuralFilterRejectionReason.MISSING_VALUE
            and self.observed_value is not None
        ):
            raise ValueError("missing-value structural rejection cannot carry observed_value")
        if (
            self.reason is StructuralFilterRejectionReason.BELOW_THRESHOLD
            and self.observed_value is None
        ):
            raise ValueError("below-threshold structural rejection requires observed_value")
        if (
            self.reason is StructuralFilterRejectionReason.BELOW_THRESHOLD
            and self.observed_value is not None
            and self.threshold is not None
            and self.observed_value >= self.threshold
        ):
            raise ValueError("below-threshold structural rejection must be below threshold")

    @classmethod
    def disabled(cls) -> StructuralFilterDecision:
        return cls(outcome=StructuralFilterOutcome.DISABLED)

    @classmethod
    def passed(cls) -> StructuralFilterDecision:
        return cls(outcome=StructuralFilterOutcome.PASSED)

    @classmethod
    def rejected(
        cls,
        *,
        field: StructuralFilterField,
        reason: StructuralFilterRejectionReason,
        observed_value: int | None,
        threshold: int,
    ) -> StructuralFilterDecision:
        return cls(
            outcome=StructuralFilterOutcome.REJECTED,
            field=field,
            reason=reason,
            observed_value=observed_value,
            threshold=threshold,
        )

    def to_dict(self) -> dict[str, Any]:
        """Canonical schema-15 observation representation."""
        return {
            "outcome": self.outcome.value,
            "field": self.field.value if self.field is not None else None,
            "reason": self.reason.value if self.reason is not None else None,
            "observed_value": self.observed_value,
            "threshold": self.threshold,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> StructuralFilterDecision:
        """Strictly parse the canonical persisted representation."""
        expected = {"outcome", "field", "reason", "observed_value", "threshold"}
        if set(value) != expected:
            raise ValueError(
                "structural-filter decision fields mismatch: "
                f"expected={sorted(expected)!r} actual={sorted(value)!r}"
            )
        try:
            outcome = StructuralFilterOutcome(value["outcome"])
            field = StructuralFilterField(value["field"]) if value["field"] is not None else None
            reason = (
                StructuralFilterRejectionReason(value["reason"])
                if value["reason"] is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid structural-filter decision enum: {exc}") from exc
        observed_value = value["observed_value"]
        threshold = value["threshold"]
        for name, raw in (("observed_value", observed_value), ("threshold", threshold)):
            if raw is not None and (type(raw) is not int):
                raise ValueError(f"structural-filter {name} must be int or null")
        return cls(
            outcome=outcome,
            field=field,
            reason=reason,
            observed_value=observed_value,
            threshold=threshold,
        )
