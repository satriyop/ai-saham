"""Pre-open RiskInputsBuilder — always self-fetch (returns None GateContext).

Layer: Application
"""

from __future__ import annotations

from datetime import date

from src.domain.rules.risk_gate import GateContext


class PreOpenRiskInputsBuilder:
    """Pre-open has no pre-loaded fundamentals; RiskEngine.assess self-fetches."""

    def build(self, candidate: object, *, as_of_date: date) -> GateContext | None:
        return None
