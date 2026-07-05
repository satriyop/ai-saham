"""
DecisionPolicyService resolves regime/setup decision constraints.

Layer: Application
Depends on: domain value objects and application config dataclasses only.
No IO, providers, repositories, or CLI formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.use_case.assess_signal_use_case import DecisionPolicyConfig
from src.domain.value_objects.decision_constraints import DecisionConstraints
from src.domain.value_objects.signal_assessment import EntryQuality

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext


_ORDER: dict[str, int] = {
    EntryQuality.AVOID.value: 0,
    EntryQuality.WATCH.value: 1,
    EntryQuality.ENTER.value: 2,
}


@dataclass(frozen=True)
class DecisionPolicyResult:
    entry_quality: EntryQuality
    constraints: DecisionConstraints


class DecisionPolicyService:
    """Resolve A1 decision constraints without mutating raw signal score."""

    def __init__(self, config: DecisionPolicyConfig | None = None) -> None:
        self._config = config or DecisionPolicyConfig()

    def resolve(
        self,
        *,
        entry_quality: EntryQuality,
        score: int,
        coverage_score: float,
        conviction_score: float,
        market_context: "MarketContext | None",
        setup_family: str | None = None,
    ) -> DecisionPolicyResult:
        regime = market_context.regime.value if market_context else "RISK_ON"
        regime_policy = self._config.regime_policy[regime]
        reasons: list[str] = []

        max_decision = regime_policy.max_decision
        if not regime_policy.enter_allowed:
            max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
            reasons.append(f"{regime} disables ENTER")

        setup_key = _normalize_setup_family(setup_family)
        setup_action_name: str | None = None
        if setup_key is not None:
            setup_action_name = (
                self._config.setup_regime_policy
                .get(setup_key, {})
                .get(regime)
            )
            if setup_action_name is not None:
                action_cfg = self._config.setup_regime_actions[setup_action_name]
                before = max_decision
                max_decision = _stricter(max_decision, action_cfg.max_decision)
                if _ORDER[action_cfg.max_decision] < _ORDER[before]:
                    reasons.append(
                        f"Setup {setup_key} tightens {regime} to {action_cfg.max_decision}"
                    )
                elif _ORDER[action_cfg.max_decision] > _ORDER[before]:
                    reasons.append(
                        "Setup-specific policy cannot override regime ENTER block"
                    )

        if (
            regime_policy.enter_allowed
            and entry_quality == EntryQuality.ENTER
            and regime_policy.enter_threshold is not None
            and score < regime_policy.enter_threshold
        ):
            max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
            reasons.append(
                f"{regime} ENTER requires score >= {regime_policy.enter_threshold}"
            )

        if (
            entry_quality in {EntryQuality.ENTER, EntryQuality.WATCH}
            and score < regime_policy.watch_threshold
        ):
            max_decision = _stricter(max_decision, EntryQuality.AVOID.value)
            reasons.append(
                f"{regime} WATCH requires score >= {regime_policy.watch_threshold}"
            )

        if regime_policy.enter_allowed and entry_quality == EntryQuality.ENTER:
            if coverage_score < regime_policy.min_coverage:
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append(
                    f"{regime} ENTER requires coverage >= {regime_policy.min_coverage:.0%}"
                )
            if conviction_score < regime_policy.min_conviction:
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append(
                    f"{regime} ENTER requires conviction >= {regime_policy.min_conviction:.0%}"
                )

        constrained = _cap_entry(entry_quality, max_decision)
        constraints = DecisionConstraints(
            max_decision=max_decision,
            regime=regime if market_context else None,
            regime_enter_allowed=regime_policy.enter_allowed,
            regime_size_multiplier=regime_policy.regime_size_multiplier,
            setup_family=setup_key,
            setup_regime_action=setup_action_name,
            effective_size_multiplier=regime_policy.regime_size_multiplier,
            constraint_reasons=tuple(reasons),
        )
        return DecisionPolicyResult(entry_quality=constrained, constraints=constraints)


def _normalize_setup_family(setup_family: str | None) -> str | None:
    if not setup_family:
        return None
    return setup_family.strip().lower().replace("-", "_")


def _stricter(left: str, right: str) -> str:
    if left not in _ORDER:
        raise ValueError(f"Invalid decision name: {left}")
    if right not in _ORDER:
        raise ValueError(f"Invalid decision name: {right}")
    return left if _ORDER[left] <= _ORDER[right] else right


def _cap_entry(entry_quality: EntryQuality, max_decision: str) -> EntryQuality:
    if max_decision not in _ORDER:
        raise ValueError(f"Invalid decision name: {max_decision}")
    if _ORDER[entry_quality.value] <= _ORDER[max_decision]:
        return entry_quality
    return EntryQuality(max_decision)
