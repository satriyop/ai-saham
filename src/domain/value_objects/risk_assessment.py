"""
RiskAssessment value object.

Represents the outcome of evaluating an indicator snapshot
against a specific risk profile's rules.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile


@dataclass(frozen=True)
class RiskAssessment:
    """
    Immutable result of risk evaluation for a single snapshot.

    Contains the risk level determination along with supporting
    metadata for transparency and auditability.

    Attributes:
        profile: The risk profile used for evaluation (RiskProfile enum or string
                 for custom YAML-based rules)
        risk_level: The determined risk level (HIGH_RISK, MODERATE, LOW_RISK)
        confidence: Rule alignment strength (0, 50, or 100)
        rationale: Human-readable explanations for the assessment
        snapshot_date: Date of the indicator snapshot evaluated
        indicators: The full indicator snapshot that was evaluated
    """

    profile: RiskProfile | str  # str for custom YAML rules
    risk_level: RiskLevel
    confidence: int
    rationale: tuple[str, ...]  # Immutable tuple for frozen dataclass
    snapshot_date: date
    indicators: IndicatorSnapshot
    gate_triggered: str | None = None     # set when a RiskGate overrode the technical signal
    gate_is_structural: bool | None = None  # True=structural, False=execution, None=no gate

    def __post_init__(self) -> None:
        """Validate confidence is within valid range."""
        if not (0 <= self.confidence <= 100):
            raise ValueError(f"Confidence must be 0-100, got {self.confidence}")

    @property
    def profile_name(self) -> str:
        """Return profile name as string for display."""
        if isinstance(self.profile, str):
            return self.profile
        return self.profile.value

    @property
    def is_custom_profile(self) -> bool:
        """Return True if this assessment used custom YAML rules."""
        return isinstance(self.profile, str)

    @property
    def risk_level_name(self) -> str:
        """Return risk level name as string for display."""
        return self.risk_level.value.upper()

    @property
    def rationale_list(self) -> list[str]:
        """Return rationale as a mutable list for convenience."""
        return list(self.rationale)
