"""
DecisionPolicyService resolves regime/setup decision constraints.

Layer: Application
Depends on: domain value objects and application config dataclasses only.
No IO, providers, repositories, or CLI formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services.signal_engine_config import DecisionPolicyConfig
from src.domain.value_objects.decision_constraints import DecisionConstraints
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.domain.value_objects.signal_assessment import EntryQuality

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot


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
        setup_phase: "SetupPhaseSnapshot | None" = None,
        setup_entry_authority: bool = True,
        setup_can_enter_from_phases: tuple[str, ...] = (),
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
            # In enter-allowed regimes: floors gate ENTER → cap to WATCH if not met
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

        if not regime_policy.enter_allowed and entry_quality in {EntryQuality.ENTER, EntryQuality.WATCH}:
            # In disabled regimes (RISK_OFF/VOLATILE): floors govern WATCH diagnostic quality
            # — below floor means insufficient evidence for even a watchlist entry
            if coverage_score < regime_policy.min_coverage:
                max_decision = _stricter(max_decision, EntryQuality.AVOID.value)
                reasons.append(
                    f"{regime} WATCH requires coverage >= {regime_policy.min_coverage:.0%} "
                    f"(got {coverage_score:.0%})"
                )
            if conviction_score < regime_policy.min_conviction:
                max_decision = _stricter(max_decision, EntryQuality.AVOID.value)
                reasons.append(
                    f"{regime} WATCH requires conviction >= {regime_policy.min_conviction:.0%} "
                    f"(got {conviction_score:.0%})"
                )

        # ── A2: regime quality caps (tightening-only; never relax A1 caps) ────
        if market_context is not None:
            regime_confidence = getattr(market_context, "regime_confidence", None)
            regime_stability  = getattr(market_context, "regime_stability", None)

            if (
                self._config.regime_transitioning_cap_enter
                and regime_stability == "TRANSITIONING"
                and regime_policy.enter_allowed
            ):
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append("Regime TRANSITIONING — ENTER capped to WATCH")

            if (
                regime_confidence is not None
                and regime_confidence < self._config.regime_confidence_min_enter
                and regime_policy.enter_allowed
            ):
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append(
                    f"Low regime_confidence ({regime_confidence:.2f} < "
                    f"{self._config.regime_confidence_min_enter:.2f}) — ENTER capped"
                )

        if setup_phase is not None:
            if setup_phase.current_phase in {
                SetupPhaseState.DISTRIBUTION,
                SetupPhaseState.FAILED,
            }:
                max_decision = _stricter(max_decision, EntryQuality.AVOID.value)
                reasons.append(
                    f"Setup phase {setup_phase.current_phase.value} blocks entry"
                )
            elif setup_phase.current_phase == SetupPhaseState.EXHAUSTION:
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append("Setup phase EXHAUSTION caps ENTER to WATCH")
            # Benchmark excess-return evidence (SetupEvidence.
            # benchmark_excess_return_5_session/20_session) is
            # DIAGNOSTIC_UNVALIDATED and intentionally NOT parsed here — see
            # tasks/backlog/audit_signal_refactor_contract.md Task HIGH-1.
            # setup_phase.reasons is never scanned for authority strings.
            if setup_phase.sequence_valid is False:
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append("Setup phase sequence invalid — ENTER capped to WATCH")

        # ── Setup entry authority (explicit config; never inferred from name) ──
        # A setup MATCH alone must not create ENTER. entry_authority and
        # can_enter_from_phases come from config/swing_setups.yaml via
        # SetupEvidence — this is the only place that enforces them.
        if entry_quality == EntryQuality.ENTER:
            setup_label = setup_key or "setup"
            if not setup_entry_authority:
                max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                reasons.append(
                    f"Setup {setup_label} has no standalone entry authority"
                )
            elif setup_can_enter_from_phases:
                if setup_phase is None:
                    max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                    reasons.append(
                        f"Setup {setup_label} requires setup phase for ENTER"
                    )
                elif setup_phase.current_phase.value not in setup_can_enter_from_phases:
                    max_decision = _stricter(max_decision, EntryQuality.WATCH.value)
                    reasons.append(
                        f"Setup {setup_label} requires phase "
                        f"{', '.join(setup_can_enter_from_phases)} for ENTER; "
                        f"current phase {setup_phase.current_phase.value}"
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
