"""
FlowConfirmationEvidenceBuilder — application service (Phase 3).

Groups correlated broker/flow sub-signals into a FlowConfirmationEvidence VO.
Extracts scored sub-components from an existing ForeignFlowEvidence (or
AccumulationCandidate) and adds the Bandar operator snapshot as a second
dimension.

BB is explicitly excluded: it lives in SetupEvidence. RSI is also excluded
(price-action, not broker flow). Only keys: cons, streak, vwap, flow, inst.

Layer: Application
Depends on: domain VOs (FlowConfirmationEvidence, Direction, Freshness) + stdlib.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)

# Sub-signal keys extracted from the ForeignFlowScoreBreakdown.
# BB excluded (SetupEvidence owns it). RSI excluded (price-action, not flow).
_FLOW_SIGNAL_KEYS = ("cons", "streak", "vwap", "flow", "inst")

# Max weight for each sub-signal (from ForeignFlowScorePolicy defaults).
# Used for direction thresholding and group strength normalization.
_FLOW_SIGNAL_WEIGHTS: dict[str, float] = {
    "cons": 40.0,
    "streak": 30.0,
    "vwap": 20.0,
    "flow": 10.0,
    "inst": 15.0,  # max achievable = cluster_points (CLUSTER > STABLE)
}

# Normalization denominator: sum of max weights for the 5 included sub-signals
# (cons=40 + streak=30 + vwap=20 + flow=10 + inst=15 = 115).
# BB (10) and RSI (10) are excluded, so 120 is not the correct ceiling here.
_FLOW_MAX_SCORE = 115.0

# Default group cap for the flow confirmation group.
# Even when bandar + foreign flow are both max-bullish, the combined group
# vote is capped to prevent double-counting correlated broker data.
_DEFAULT_GROUP_CAP = 0.80

# Bandar broad_score ranges from -12 to +12 (6 label components × ±2 max each).
_BANDAR_MAX_SCORE = 12.0


class FlowConfirmationEvidenceBuilder:
    """Builds diagnostic FlowConfirmationEvidence from prior flow/bandar results."""

    def build(
        self,
        candidate: Any,  # AccumulationCandidate; Any avoids domain coupling
        *,
        group_cap: float = _DEFAULT_GROUP_CAP,
        analysis_date: date | None = None,
    ) -> FlowConfirmationEvidence:
        ticker = getattr(candidate, "ticker", None) or ""
        snapshot_date = analysis_date or self._resolve_snapshot_date(candidate)

        # --- Extract foreign flow sub-signals --------------------------------
        flow_evidence = getattr(candidate, "foreign_flow_evidence", None) if candidate else None
        breakdown_dict = self._extract_breakdown(flow_evidence)
        flow_freshness = Freshness.FRESH if flow_evidence is not None else Freshness.MISSING

        flow_signals = tuple(
            self._make_sub_signal(key, breakdown_dict, flow_freshness)
            for key in _FLOW_SIGNAL_KEYS
        )
        flow_score_ex_bb = round(sum(s.score for s in flow_signals), 1)

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
        flow_strength = flow_score_ex_bb / _FLOW_MAX_SCORE if flow_evidence is not None else 0.0

        if bandar_broad_score is not None:
            bandar_strength = (bandar_broad_score + _BANDAR_MAX_SCORE) / (2.0 * _BANDAR_MAX_SCORE)
            uncapped_strength = (flow_strength + bandar_strength) / 2.0
        else:
            uncapped_strength = flow_strength

        capped_strength = min(uncapped_strength, group_cap)
        group_freshness = flow_freshness  # group is fresh iff flow evidence is fresh

        return FlowConfirmationEvidence(
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

    @staticmethod
    def _extract_breakdown(flow_evidence: Any) -> dict[str, float]:
        """Extract {key: score} from ForeignFlowEvidence.component_breakdown."""
        if flow_evidence is None:
            return {}
        breakdown = getattr(flow_evidence, "component_breakdown", None)
        if not breakdown:
            return {}
        return {k: float(v) for k, v in breakdown if isinstance(k, str)}

    @staticmethod
    def _make_sub_signal(
        key: str,
        breakdown: dict[str, float],
        freshness: Freshness,
    ) -> FlowSubSignal:
        score = breakdown.get(key, 0.0)
        weight = _FLOW_SIGNAL_WEIGHTS.get(key, 1.0)
        direction = Direction.BULLISH if score > 0 else Direction.NEUTRAL
        return FlowSubSignal(
            key=key,
            score=round(score, 1),
            weight=weight,
            direction=direction,
            freshness=freshness,
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
