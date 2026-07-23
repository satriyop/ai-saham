"""
RiskAssessment value object.

Represents the outcome of running risk gates against a snapshot. The verdict
is purely `gate_triggered` (str | None): a gate fired, or none did. There is
no intermediate RiskLevel and no assessment-level confidence — only the
confidence of the gate that fired (gate_confidence).

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


@dataclass(frozen=True)
class RiskAssessment:
    """
    Immutable result of risk evaluation for a single snapshot.

    Attributes:
        rationale: Human-readable explanations for the assessment
        snapshot_date: Date of the indicator snapshot evaluated
        indicators: The full indicator snapshot that was evaluated
        gate_triggered: The verdict — name of the gate that fired, or None
        gate_is_structural: True=structural, False=execution, None=no gate
        gate_confidence: Confidence of the gate that fired, or None
    """

    rationale: tuple[str, ...]
    snapshot_date: date
    indicators: IndicatorSnapshot
    gate_triggered: str | None = None
    gate_is_structural: bool | None = None
    gate_confidence: int | None = None

    @property
    def rationale_list(self) -> list[str]:
        """Return rationale as a mutable list for convenience."""
        return list(self.rationale)

    # ── Display-only derived verdict (no intermediate RiskLevel exists) ──────
    @property
    def risk_level_name(self) -> str:
        """Gate-based verdict for display: BLOCKED when a gate fired, else OPEN."""
        return "BLOCKED" if self.gate_triggered else "OPEN"

    @property
    def confidence(self) -> int:
        """Confidence of the gate that fired (0 when no gate fired)."""
        return self.gate_confidence or 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat(),
            "gate_triggered": self.gate_triggered,
            "gate_is_structural": self.gate_is_structural,
            "gate_confidence": self.gate_confidence,
            "confidence": self.confidence,
            "rationale": list(self.rationale),
            "indicators": self.indicators.to_dict(),
        }
