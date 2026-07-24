"""DTOs for risk assessment use cases.

Layer: Application
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_gate_audit import (
    GateContextCompleteness,
    GateEvaluationRecord,
)
from src.domain.value_objects.sentiment import SentimentSnapshot


@dataclass
class AssessRiskRequest:
    """Request DTO for risk assessment."""

    ticker: str
    sma_period: int = 20
    ema_period: int = 20
    rsi_period: int = 14
    rules_file: Path | str | None = None  # Custom YAML rules file
    sentiment: SentimentSnapshot | None = None  # Optional sentiment context
    # Phase B: pre-loaded non-technical data for gate evaluation.
    # If provided and the use case has gates configured, gates run before
    # the technical rule engine (structural) and after (execution).
    gate_context: GateContext | None = None


@dataclass
class AssessRiskResponse:
    """Response DTO containing risk assessment result."""

    ticker: str
    assessment: RiskAssessment
    sma_period: int
    ema_period: int
    rsi_period: int
    coverage_warning: str | None = None
    # Package C2 audit — does not affect TradeSetup / verdict consumers.
    gate_evaluations: tuple[GateEvaluationRecord, ...] = field(default_factory=tuple)
    gate_context_completeness: GateContextCompleteness | None = None

    @property
    def gate_triggered(self) -> str | None:
        """Delegates to RiskAssessment — single source of truth."""
        return self.assessment.gate_triggered

    @property
    def risk_level(self) -> str:
        """Gate-based risk indicator for display."""
        if self.assessment.gate_triggered:
            return "BLOCKED"
        return "open"

    @property
    def confidence(self) -> int:
        """Confidence of the gate that fired (0 when none)."""
        return self.assessment.gate_confidence or 0


@dataclass
class AssessRiskTrendResponse:
    """Response DTO for risk trend over N days."""

    ticker: str
    history: list[tuple[date, str, int]]  # (date, indicator_reading, confidence)
    direction: str  # "IMPROVING" | "STABLE" | "DETERIORATING"
    days_in_current: int
