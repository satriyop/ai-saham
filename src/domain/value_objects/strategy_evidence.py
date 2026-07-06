"""Diagnostic strategy evidence produced from validated strategy YAMLs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class StrategyEvidenceOutcome(Enum):
    """Snapshot outcome from diagnostic strategy rule evaluation."""

    MATCHED = "MATCHED"
    NOT_MATCHED = "NOT_MATCHED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class StrategyRuleEvidence:
    """Evidence for the rule selected by a strategy YAML at one snapshot."""

    strategy_name: str
    rule_name: str | None
    rule_outcome: str | None
    evidence_route: str
    setup_family: str | None = None
    setup_phase: str | None = None
    rationale: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy_name:
            raise ValueError("strategy_name cannot be empty")
        if not self.evidence_route:
            raise ValueError("evidence_route cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "rule_name": self.rule_name,
            "rule_outcome": self.rule_outcome,
            "evidence_route": self.evidence_route,
            "setup_family": self.setup_family,
            "setup_phase": self.setup_phase,
            "rationale": list(self.rationale),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyRuleEvidence":
        return cls(
            strategy_name=str(data["strategy_name"]),
            rule_name=data.get("rule_name"),
            rule_outcome=data.get("rule_outcome"),
            evidence_route=str(data.get("evidence_route") or "strategy_yaml"),
            setup_family=data.get("setup_family"),
            setup_phase=data.get("setup_phase"),
            rationale=tuple(str(v) for v in data.get("rationale") or ()),
        )


@dataclass(frozen=True)
class StrategyEvidence:
    """Diagnostic strategy evidence for a ticker snapshot.

    This value object is descriptive only. It must not override canonical
    setup phase state, signal score, decision policy, or TradeSetup sizing.
    """

    ticker: str
    snapshot_date: date
    strategy_name: str
    outcome: StrategyEvidenceOutcome
    matched_rule: StrategyRuleEvidence | None = None
    coverage_score: float | None = None
    conviction_score: float | None = None
    freshness_score: float | None = None
    rationale: tuple[str, ...] = ()
    unavailable_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if not self.strategy_name:
            raise ValueError("strategy_name cannot be empty")
        for name in ("coverage_score", "conviction_score", "freshness_score"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "strategy_name": self.strategy_name,
            "outcome": self.outcome.value,
            "matched_rule": (
                self.matched_rule.to_dict() if self.matched_rule is not None else None
            ),
            "coverage_score": self.coverage_score,
            "conviction_score": self.conviction_score,
            "freshness_score": self.freshness_score,
            "rationale": list(self.rationale),
            "unavailable_reasons": list(self.unavailable_reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyEvidence":
        matched_rule = data.get("matched_rule")
        return cls(
            ticker=str(data["ticker"]).upper(),
            snapshot_date=(
                data["snapshot_date"]
                if isinstance(data["snapshot_date"], date)
                else date.fromisoformat(str(data["snapshot_date"]))
            ),
            strategy_name=str(data["strategy_name"]),
            outcome=StrategyEvidenceOutcome(data["outcome"]),
            matched_rule=(
                StrategyRuleEvidence.from_dict(matched_rule)
                if isinstance(matched_rule, dict)
                else None
            ),
            coverage_score=_optional_float(data.get("coverage_score")),
            conviction_score=_optional_float(data.get("conviction_score")),
            freshness_score=_optional_float(data.get("freshness_score")),
            rationale=tuple(str(v) for v in data.get("rationale") or ()),
            unavailable_reasons=tuple(
                str(v) for v in data.get("unavailable_reasons") or ()
            ),
            metadata=dict(data.get("metadata") or {}),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
