"""
Setup evaluation value objects.

Layer: Domain
"""

from dataclasses import dataclass
from enum import Enum


class SetupMatch(str, Enum):
    """Pattern-fit result for a named setup.

    This is not a trade action. Final ENTER/WATCH/AVOID/BLOCKED decisions
    belong to TradeSetup.
    """

    MATCH = "MATCH"
    PARTIAL = "PARTIAL"
    NO_MATCH = "NO_MATCH"


@dataclass(frozen=True)
class SetupGate:
    label: str
    passed: bool
    actual: str
    required: str


@dataclass(frozen=True)
class SetupEvaluation:
    name: str
    match: SetupMatch
    gates: tuple[SetupGate, ...]
    failed_reasons: tuple[str, ...]
    # Entry authority metadata — sourced from config/swing_setups.yaml via
    # EvaluateSwingSetupUseCase, never inferred from setup name. Defaults exist
    # only for backward compatibility with callers that construct SetupEvaluation
    # without config; config/swing_setups.yaml is explicit for every current setup.
    family: str = "unknown"
    entry_authority: bool = True
    can_enter_from_phases: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Compatibility in workflow logic: only a full setup match passes."""
        return self.match == SetupMatch.MATCH

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "match": self.match.value,
            "passed": self.passed,
            "failed_reasons": list(self.failed_reasons),
            "family": self.family,
            "entry_authority": self.entry_authority,
            "can_enter_from_phases": list(self.can_enter_from_phases),
            "gates": [
                {
                    "label": gate.label,
                    "passed": gate.passed,
                    "actual": gate.actual,
                    "required": gate.required,
                }
                for gate in self.gates
            ],
        }
