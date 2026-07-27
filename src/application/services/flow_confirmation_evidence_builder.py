"""
FlowConfirmationEvidenceBuilder — application service (Phase 3).

Groups correlated broker/flow sub-signals into a FlowConfirmationEvidence VO.
Extracts scored sub-components from an existing ForeignFlowEvidence (or
AccumulationCandidate) and adds the Bandar operator snapshot as a second
dimension.

BB is explicitly excluded: it is setup-phase/trigger-readiness diagnostic
owned by SetupEvidence, not broker-flow evidence. RSI is also excluded: it is
price-action, not broker flow. Only keys: cons, streak, vwap, flow, inst.

Layer: Application
Depends on: domain VOs (FlowConfirmationEvidence, Direction, Freshness) +
AccumScorePolicy (application-layer value object, not YAML) + stdlib.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.application.dto.built_evidence import BuiltFlowEvidence
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.value_objects.accum_score_breakdown import (
    FOREIGN_FLOW_COMPONENT_KEYS,
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)
from src.domain.value_objects.canonical_signal_evidence_input import (
    BrokerDailyFlowRowIdentity,
    BrokerSummaryRowIdentity,
    FlowProvenance,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence

# Sub-signal keys extracted from the AccumScoreBreakdown.
# BB excluded (SetupEvidence owns it). RSI excluded (price-action, not flow).
_FLOW_SIGNAL_KEYS = ("cons", "streak", "vwap", "flow", "inst")

# Default group cap for the flow confirmation group.
# Even when bandar + foreign flow are both max-bullish, the combined group
# vote is capped to prevent double-counting correlated broker data.
_DEFAULT_GROUP_CAP = 0.80

# Bandar broad_score ranges from -12 to +12 (6 label components × ±2 max each).
_BANDAR_MAX_SCORE = 12.0


class FlowConfirmationEvidenceBuilder:
    """Builds diagnostic FlowConfirmationEvidence from prior flow/bandar results.

    Max weights for direction thresholding and group-strength normalization
    are derived from the injected AccumScorePolicy — the same policy
    ScoreAccumUseCase uses to compute the breakdown this builder reads.
    This prevents the drift that occurred when this builder previously kept
    its own hardcoded copy of the weights (see ADR-039): a policy change (via
    config/accumulation_screener.yaml or direct construction) now propagates
    here automatically instead of requiring a matching code edit.
    """

    def __init__(
        self,
        accum_score_policy: AccumScorePolicy | None = None,
    ) -> None:
        policy = accum_score_policy or AccumScorePolicy()
        self._flow_signal_weights: dict[str, float] = {
            "cons": policy.consistency.weight if policy.consistency.enabled else 0.0,
            "streak": policy.streak.weight if policy.streak.enabled else 0.0,
            "vwap": policy.vwap_discount.weight if policy.vwap_discount.enabled else 0.0,
            "flow": policy.foreign_flow_ratio.weight if policy.foreign_flow_ratio.enabled else 0.0,
            # max achievable = cluster_points (CLUSTER > STABLE)
            "inst": policy.bci.cluster_points if policy.bci.enabled else 0.0,
        }
        self._component_contracts: dict[str, tuple[bool, float]] = {
            "cons": (policy.consistency.enabled, policy.consistency.weight),
            "streak": (policy.streak.enabled, policy.streak.weight),
            "vwap": (policy.vwap_discount.enabled, policy.vwap_discount.weight),
            "rsi": (policy.rsi_headroom.enabled, policy.rsi_headroom.weight),
            "flow": (policy.foreign_flow_ratio.enabled, policy.foreign_flow_ratio.weight),
            "bb": (policy.bb_squeeze.enabled, policy.bb_squeeze.weight),
            "inst": (policy.bci.enabled, policy.bci.cluster_points),
        }

    def build(
        self,
        candidate: Any,  # AccumulationCandidate; Any avoids domain coupling
        *,
        consumed_broker_summaries: "tuple[BrokerSummary, ...]",
        consumed_broker_daily_flows: "tuple[BrokerDailyFlow, ...]",
        group_cap: float = _DEFAULT_GROUP_CAP,
        analysis_date: date | None = None,
    ) -> BuiltFlowEvidence:
        ticker = getattr(candidate, "ticker", None) or ""
        snapshot_date = analysis_date or self._resolve_snapshot_date(candidate)

        # --- Extract foreign flow sub-signals --------------------------------
        flow_evidence = getattr(candidate, "foreign_flow_evidence", None) if candidate else None
        components = self._extract_components(flow_evidence)

        flow_signals_list: list[FlowSubSignal] = []
        missing: list[str] = []
        available_weight = 0.0
        enabled_weight = 0.0
        available_score = 0.0

        for key in _FLOW_SIGNAL_KEYS:
            policy_weight = self._flow_signal_weights.get(key, 0.0)
            component = components.get(key)
            sub = self._make_sub_signal(key, component, policy_weight)
            if sub is None:
                continue
            flow_signals_list.append(sub)
            if sub.freshness is Freshness.MISSING:
                missing.append(key)
            if sub.weight > 0:
                enabled_weight += sub.weight
                if sub.freshness is Freshness.FRESH:
                    available_weight += sub.weight
                    available_score += sub.score

        flow_signals = tuple(flow_signals_list)
        flow_score_ex_bb = round(available_score, 1)
        component_coverage = (
            min(1.0, available_weight / enabled_weight) if enabled_weight > 0 else 0.0
        )

        confirmation_status = (
            getattr(flow_evidence, "confirmation_status", None)
            if flow_evidence is not None
            else "WEAK"
        ) or "WEAK"
        if confirmation_status not in {"CONFIRMED", "WATCH_ZONE", "WEAK"}:
            confirmation_status = "WEAK"

        flow_direction = (
            getattr(flow_evidence, "flow_direction", None)
            if flow_evidence is not None
            else "UNKNOWN"
        ) or "UNKNOWN"
        if flow_direction not in {"POSITIVE", "NEGATIVE", "FLAT", "UNKNOWN"}:
            flow_direction = "UNKNOWN"

        # --- Bandar operator sub-signal --------------------------------------
        bandar_detector = getattr(candidate, "bandar_detector", None) if candidate else None
        bandar_broad_score: int | None = None
        bandar_direction = Direction.NEUTRAL
        bandar_freshness = Freshness.MISSING

        if bandar_detector is not None:
            broad_score = getattr(bandar_detector, "broad_score", None)
            if broad_score is not None:
                bandar_broad_score = int(broad_score)
                bandar_direction = self._bandar_direction(bandar_broad_score)
                bandar_freshness = Freshness.FRESH

        # --- BCI context -----------------------------------------------------
        bci_label = getattr(candidate, "bci_label", None) if candidate else None
        bci_tier1_count = int(getattr(candidate, "bci_tier1_count", 0) or 0) if candidate else 0

        # --- Group aggregate with cap ----------------------------------------
        # Directional strength denominator uses available enabled flow-component
        # weights only. True-zero AVAILABLE components remain in that denominator.
        # MISSING components are excluded from the directional denominator.
        flow_strength = available_score / available_weight if available_weight > 0 else 0.0

        if bandar_broad_score is not None:
            bandar_strength = (bandar_broad_score + _BANDAR_MAX_SCORE) / (2.0 * _BANDAR_MAX_SCORE)
            uncapped_strength = (flow_strength + bandar_strength) / 2.0
        else:
            uncapped_strength = flow_strength

        capped_strength = min(uncapped_strength, group_cap)
        # Completeness is represented by component statuses and coverage. It
        # must not be mislabeled as temporal staleness.
        group_freshness = Freshness.FRESH if flow_evidence is not None else Freshness.MISSING

        evidence = FlowConfirmationEvidence(
            ticker=ticker,
            snapshot_date=snapshot_date,
            flow_signals=flow_signals,
            flow_score_ex_bb=flow_score_ex_bb,
            confirmation_status=confirmation_status,
            flow_direction=flow_direction,
            bandar_broad_score=bandar_broad_score,
            bandar_direction=bandar_direction,
            bandar_freshness=bandar_freshness,
            bci_label=bci_label,
            bci_tier1_count=bci_tier1_count,
            uncapped_strength=round(uncapped_strength, 4),
            capped_strength=round(capped_strength, 4),
            group_cap=group_cap,
            group_freshness=group_freshness,
        )
        if round(evidence.component_coverage, 4) != round(component_coverage, 4):
            raise ValueError("derived flow component coverage differs from builder state")
        if evidence.missing_components != tuple(missing):
            raise ValueError("derived missing flow components differ from builder state")
        provenance = FlowProvenance(
            ticker=ticker,
            broker_summary_rows=tuple(
                BrokerSummaryRowIdentity(ticker=s.ticker, date=s.date, source=s.source)
                for s in consumed_broker_summaries
            ),
            broker_daily_flow_rows=tuple(
                BrokerDailyFlowRowIdentity(
                    ticker=f.ticker, date=f.date, broker_code=f.broker_code, source=f.source
                )
                for f in consumed_broker_daily_flows
            ),
            # Determined here from whether Bandar actually contributed to the
            # evidence just built — never mutated by a downstream caller.
            has_bandar_contributor=bandar_broad_score is not None,
        )
        return BuiltFlowEvidence(evidence=evidence, provenance=provenance)

    def _extract_components(
        self,
        flow_evidence: Any,
    ) -> dict[str, ForeignFlowComponentScore]:
        """Extract typed components from ForeignFlowEvidence."""
        if flow_evidence is None:
            return {}
        if not isinstance(flow_evidence, ForeignFlowEvidence):
            raise TypeError(
                "flow_evidence must be ForeignFlowEvidence; legacy numeric "
                "component breakdowns are not accepted"
            )
        components = flow_evidence.components_by_key
        if set(components) != FOREIGN_FLOW_COMPONENT_KEYS:
            raise ValueError("flow_evidence does not contain the canonical component set")
        for key, component in components.items():
            enabled, configured_max = self._component_contracts[key]
            if abs(component.max_points - configured_max) > 1e-9:
                raise ValueError(
                    f"flow component {key!r} max_points={component.max_points} "
                    f"does not match active policy {configured_max}"
                )
            if enabled and component.status is ForeignFlowComponentStatus.DISABLED:
                raise ValueError(f"flow component {key!r} is DISABLED but active policy enables it")
            if not enabled and component.status is not ForeignFlowComponentStatus.DISABLED:
                raise ValueError(f"flow component {key!r} must be DISABLED under the active policy")
        return components

    def _make_sub_signal(
        self,
        key: str,
        component: ForeignFlowComponentScore | None,
        policy_weight: float,
    ) -> FlowSubSignal | None:
        if policy_weight <= 0:
            # Policy-disabled: excluded from the flow group entirely.
            return None
        if component is None:
            return FlowSubSignal(
                key=key,
                score=0.0,
                weight=policy_weight,
                direction=Direction.NEUTRAL,
                freshness=Freshness.MISSING,
            )
        if component.status is ForeignFlowComponentStatus.DISABLED:
            return None
        if component.status is ForeignFlowComponentStatus.MISSING:
            return FlowSubSignal(
                key=key,
                score=0.0,
                weight=component.max_points if component.max_points > 0 else policy_weight,
                direction=Direction.NEUTRAL,
                freshness=Freshness.MISSING,
            )
        score = float(component.score_points or 0.0)
        return FlowSubSignal(
            key=key,
            score=round(score, 1),
            weight=component.max_points if component.max_points > 0 else policy_weight,
            direction=Direction.BULLISH if score > 0 else Direction.NEUTRAL,
            freshness=Freshness.FRESH,
        )

    @staticmethod
    def _bandar_direction(broad_score: int) -> Direction:
        if broad_score > 0:
            return Direction.BULLISH
        if broad_score < 0:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @staticmethod
    def _resolve_snapshot_date(candidate: Any) -> date:
        candle_date = (
            getattr(candidate, "latest_candle_date", None) if candidate is not None else None
        )
        return candle_date or date.min
