"""RiskInputsBuilder Protocol for screen adoption.

Layer: Application

Returning GateContext selects assess_with_context (pre-loaded path).
Returning None selects self-fetch (RiskEngine.assess).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from src.domain.rules.risk_gate import GateContext


@runtime_checkable
class RiskInputsBuilder(Protocol):
    """Build risk inputs for a candidate. Scenario-owned application policy."""

    def build(self, candidate: object, *, as_of_date: date) -> GateContext | None:
        """GateContext => pre-built path; None => self-fetch."""
        ...
