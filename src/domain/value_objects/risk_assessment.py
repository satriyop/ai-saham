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

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import SignalSensitivity


@dataclass(frozen=True)
class RiskAssessment:
    """
    Immutable result of risk evaluation for a single snapshot.

    Attributes:
        sensitivity: The signal sensitivity preset used (SignalSensitivity enum
                     or string for custom YAML-based rules)
        rationale: Human-readable explanations for the assessment
        snapshot_date: Date of the indicator snapshot evaluated
        indicators: The full indicator snapshot that was evaluated
        gate_triggered: The verdict — name of the gate that fired, or None
        gate_is_structural: True=structural, False=execution, None=no gate
        gate_confidence: Confidence of the gate that fired, or None
    """

    sensitivity: SignalSensitivity | str  # str for custom YAML rules
    rationale: tuple[str, ...]
    snapshot_date: date
    indicators: IndicatorSnapshot
    gate_triggered: str | None = None
    gate_is_structural: bool | None = None
    gate_confidence: int | None = None

    @property
    def sensitivity_name(self) -> str:
        """Return sensitivity preset name as string for display."""
        if isinstance(self.sensitivity, str):
            return self.sensitivity
        return self.sensitivity.value

    # Backwards-compatibility alias
    @property
    def profile_name(self) -> str:
        return self.sensitivity_name

    @property
    def is_custom_sensitivity(self) -> bool:
        """Return True if this assessment used custom YAML rules."""
        return isinstance(self.sensitivity, str)

    # Backwards-compatibility alias
    @property
    def is_custom_profile(self) -> bool:
        return self.is_custom_sensitivity

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
