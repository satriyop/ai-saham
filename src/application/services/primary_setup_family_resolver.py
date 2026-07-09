"""
Deterministic primary setup-family resolution for signal observations.

Implements the "Setup Family Source Contract" in docs/signal_refactor.md:
setup_family must be known, from an explicit source priority, before any
setup-specific policy is applied. This resolver is diagnostic/observation
plumbing only — it never grants entry authority. Final ENTER/WATCH/AVOID
decisions remain owned by SignalEngine + DecisionPolicy -> TradeSetup.

Layer: Application
Depends on: domain value objects + application/use_case value objects only.
No IO, repositories, providers, CLI, or AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
)
from src.domain.value_objects.setup_evaluation import SetupMatch

if TYPE_CHECKING:
    from src.application.use_case.evaluate_swing_setup_use_case import (
        SwingSetupCatalogConfig,
    )


# docs/signal_refactor.md "Setup Family Source Contract" default priority.
# No setup_family_priority config exists anywhere in the repo yet, so this is
# the explicit default; override via the `priority` constructor argument.
DEFAULT_SETUP_FAMILY_PRIORITY: tuple[str, ...] = (
    "foreign_bounce",
    "accumulation",
    "breakout",
    "pullback",
    "mean_reversion",
)

# docs/signal_refactor.md section 4 "Reuse Indicators, Plugins, Formulas, And
# Strategies" table — candidate setup family per validated strategy package.
STRATEGY_PACKAGE_TO_SETUP_FAMILY: dict[str, str] = {
    "foreign-accumulation": "foreign_bounce",
    "bb-breakout": "breakout",
    "williams-r-bounce": "mean_reversion",
    "bb-mean-reversion": "mean_reversion",
}


@dataclass(frozen=True)
class PrimarySetupFamilyResult:
    """Deterministic setup-family resolution result for one observation."""

    matched_setup_families: tuple[str, ...]
    primary_setup_family: str | None
    setup_family_source: str
    rationale: tuple[str, ...] = ()


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace("-", "_")


class PrimarySetupFamilyResolver:
    """Resolve matched/primary setup family from screen-time evidence.

    Source priority (docs/signal_refactor.md "Setup Family Source Contract"):
      1. explicit workflow/request setup family
      2. strategy evidence proposed setup family (only when the strategy
         actually matched a rule for this candidate — never a caller echo)
      3. detected setup families from screen evidence (named swing setups
         evaluated against the candidate's own gates)
      4. fallback: UNKNOWN / None

    Never raises. Missing/insufficient evidence resolves to the conservative
    fallback rather than fabricating a family or entry authority.
    """

    def __init__(
        self,
        *,
        priority: tuple[str, ...] = DEFAULT_SETUP_FAMILY_PRIORITY,
        strategy_family_map: dict[str, str] | None = None,
        setup_evaluator: EvaluateSwingSetupUseCase | None = None,
    ) -> None:
        self._priority = priority
        self._strategy_family_map = (
            strategy_family_map
            if strategy_family_map is not None
            else STRATEGY_PACKAGE_TO_SETUP_FAMILY
        )
        self._setup_evaluator = setup_evaluator or EvaluateSwingSetupUseCase()

    def resolve(
        self,
        *,
        candidate: Any,
        request_setup_family: str | None = None,
        strategy_evidence: Any | None = None,
        setup_phase: Any | None = None,
        flow_confirmation_evidence: Any | None = None,
        swing_setup_catalog: "SwingSetupCatalogConfig | None" = None,
    ) -> PrimarySetupFamilyResult:
        # flow_confirmation_evidence is accepted for interface parity with the
        # other screen-time evidence builders and for future family-detection
        # rules (e.g. flow-direction-gated families). It is not currently
        # authoritative for any source in the priority cascade below —
        # EvaluateSwingSetupUseCase gate matching in _from_screen_evidence
        # consumes only candidate fields.
        rationale: list[str] = []
        if setup_phase is not None:
            current_phase = getattr(setup_phase, "current_phase", None)
            if current_phase is not None:
                rationale.append(
                    f"setup phase at resolution time: {getattr(current_phase, 'value', current_phase)}"
                )

        explicit = _normalize(request_setup_family)
        if explicit is not None:
            rationale.append(f"explicit request setup_family={explicit}")
            return PrimarySetupFamilyResult(
                matched_setup_families=(explicit,),
                primary_setup_family=explicit,
                setup_family_source="explicit_request",
                rationale=tuple(rationale),
            )

        proposed = self._from_strategy_evidence(strategy_evidence, rationale)
        detected = self._from_screen_evidence(candidate, swing_setup_catalog, rationale)

        matched: list[str] = []
        if proposed is not None:
            matched.append(proposed)
        for family in detected:
            if family not in matched:
                matched.append(family)

        if not matched:
            rationale.append("no setup family matched; fallback UNKNOWN")
            return PrimarySetupFamilyResult(
                matched_setup_families=(),
                primary_setup_family=None,
                setup_family_source="fallback_unknown",
                rationale=tuple(rationale),
            )

        if proposed is not None:
            return PrimarySetupFamilyResult(
                matched_setup_families=tuple(matched),
                primary_setup_family=proposed,
                setup_family_source="strategy_evidence",
                rationale=tuple(rationale),
            )

        primary = self._select_primary(matched)
        if primary is None:
            rationale.append(
                "detected families present but none rank in configured priority"
            )
            source = "detected_unranked"
        else:
            source = "detected_screen_evidence"
        return PrimarySetupFamilyResult(
            matched_setup_families=tuple(matched),
            primary_setup_family=primary,
            setup_family_source=source,
            rationale=tuple(rationale),
        )

    def _from_strategy_evidence(
        self, strategy_evidence: Any | None, rationale: list[str]
    ) -> str | None:
        if strategy_evidence is None:
            return None
        outcome = getattr(strategy_evidence, "outcome", None)
        outcome_value = getattr(outcome, "value", outcome)
        if outcome_value != "MATCHED":
            return None
        strategy_name = getattr(strategy_evidence, "strategy_name", None)
        if not strategy_name:
            return None
        family = self._strategy_family_map.get(str(strategy_name).strip().lower())
        if family is not None:
            rationale.append(
                f"strategy '{strategy_name}' matched -> proposes setup_family={family}"
            )
        return family

    def _from_screen_evidence(
        self,
        candidate: Any,
        catalog: "SwingSetupCatalogConfig | None",
        rationale: list[str],
    ) -> list[str]:
        if candidate is None or catalog is None:
            return []
        families: list[str] = []
        for setup_name in AVAILABLE_SWING_SETUPS:
            try:
                evaluation = self._setup_evaluator.execute(
                    EvaluateSwingSetupRequest(
                        setup_name=setup_name,
                        candidate=candidate,
                        config=catalog,
                    )
                )
            except Exception:
                continue
            if evaluation.match != SetupMatch.MATCH:
                continue
            family = _normalize(evaluation.family)
            if not family or family == "unknown":
                continue
            if family not in families:
                families.append(family)
                rationale.append(
                    f"setup '{setup_name}' matched screen gates -> family={family}"
                )
        return families

    def _select_primary(self, matched: list[str]) -> str | None:
        for family in self._priority:
            if family in matched:
                return family
        return None
