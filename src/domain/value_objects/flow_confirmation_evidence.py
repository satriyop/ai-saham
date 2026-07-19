"""
FlowConfirmationEvidence — domain value object (Phase 3).

Groups the correlated broker/flow sub-signals (bandar + foreign flow) into a
single flow confirmation group with an internal cap. BB and RSI are excluded:
BB belongs in SetupEvidence (price structure); RSI is a price-action signal.

Layer: Domain
Depends on: stdlib + Direction/Freshness from factor_evidence
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from src.domain.value_objects.factor_evidence import Direction, Freshness

_VALID_CONFIRMATION_STATUS = {"CONFIRMED", "WATCH_ZONE", "WEAK"}
_VALID_FLOW_DIRECTION = {"POSITIVE", "NEGATIVE", "FLAT", "UNKNOWN"}
_VALID_FLOW_SIGNAL_KEYS = {"cons", "streak", "vwap", "flow", "inst"}


@dataclass(frozen=True)
class FlowSubSignal:
    """One scored sub-signal within the flow confirmation group."""
    key: str        # "cons" | "streak" | "vwap" | "flow" | "inst"
    score: float    # raw component score from breakdown; 0.0 when MISSING
    weight: float   # max weight (ceiling) for this component
    direction: Direction
    freshness: Freshness

    def __post_init__(self):
        if self.key not in _VALID_FLOW_SIGNAL_KEYS:
            raise ValueError(f"FlowSubSignal key must be one of {_VALID_FLOW_SIGNAL_KEYS}, got {self.key!r}")
        if self.score < 0:
            raise ValueError(f"FlowSubSignal score must be >= 0, got {self.score}")
        if self.weight < 0:
            raise ValueError(f"FlowSubSignal weight must be >= 0, got {self.weight}")
        if not isinstance(self.direction, Direction):
            raise ValueError(f"FlowSubSignal direction must be Direction enum, got {self.direction!r}")
        if not isinstance(self.freshness, Freshness):
            raise ValueError(f"FlowSubSignal freshness must be Freshness enum, got {self.freshness!r}")

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "score": self.score,
            "weight": self.weight,
            "direction": self.direction.value,
            "freshness": self.freshness.value,
        }


@dataclass(frozen=True)
class FlowConfirmationEvidence:
    """Immutable diagnostic record grouping all broker/flow sub-signals.

    BB and RSI excluded:
    - BB: belongs in SetupEvidence (price structure, not flow confirmation)
    - RSI: price-action signal, not broker flow evidence

    This object is diagnostic only in Phase 3; it feeds the replacement
    aggregator in Phase 4 as a scored evidence group.
    """
    ticker: str
    snapshot_date: date
    # Foreign flow sub-signals (bb and rsi excluded)
    flow_signals: tuple[FlowSubSignal, ...]
    flow_score_ex_bb: float       # sum of available flow_signals.score
    confirmation_status: str      # "CONFIRMED" | "WATCH_ZONE" | "WEAK"
    flow_direction: str           # "POSITIVE" | "NEGATIVE" | "FLAT" | "UNKNOWN"
    # Bandar (smart money operator) sub-signal — Stockbit only
    bandar_broad_score: int | None  # -12 to +12; None = MISSING
    bandar_direction: Direction
    bandar_freshness: Freshness     # MISSING if no Stockbit snapshot
    # BCI smart-money context
    bci_label: str | None           # "CLUSTER" | "STABLE" | "RETAIL-LED" | None
    bci_tier1_count: int            # count of distinct Tier 1 institutional brokers
    # Group aggregate with cap (Phase 4 uses capped_strength as scoring input)
    uncapped_strength: float  # 0.0–1.0 combined, before cap
    capped_strength: float    # 0.0–1.0, after group_cap applied
    group_cap: float          # cap ceiling (default 0.80)
    group_freshness: Freshness
    # Weighted coverage of enabled institutional-flow components only
    # (cons, streak, vwap, flow, inst). RSI/BB never enter this denominator.
    def __post_init__(self):
        if self.confirmation_status not in _VALID_CONFIRMATION_STATUS:
            raise ValueError(
                f"FlowConfirmationEvidence confirmation_status must be one of "
                f"{_VALID_CONFIRMATION_STATUS}, got {self.confirmation_status!r}"
            )
        if self.flow_direction not in _VALID_FLOW_DIRECTION:
            raise ValueError(
                f"FlowConfirmationEvidence flow_direction must be one of "
                f"{_VALID_FLOW_DIRECTION}, got {self.flow_direction!r}"
            )
        if self.flow_score_ex_bb < 0:
            raise ValueError(f"FlowConfirmationEvidence flow_score_ex_bb must be >= 0, got {self.flow_score_ex_bb}")
        if not (0.0 <= self.capped_strength <= 1.0):
            raise ValueError(f"FlowConfirmationEvidence capped_strength must be 0.0–1.0, got {self.capped_strength}")
        if not (0.0 < self.group_cap <= 1.0):
            raise ValueError(f"FlowConfirmationEvidence group_cap must be (0.0, 1.0], got {self.group_cap}")
        keys = [signal.key for signal in self.flow_signals]
        if len(keys) != len(set(keys)):
            raise ValueError(f"flow_signals keys must be unique, got {keys}")
        expected_score = round(sum(signal.score for signal in self.flow_signals), 1)
        if round(self.flow_score_ex_bb, 1) != expected_score:
            raise ValueError(
                "flow_score_ex_bb must equal the sum of flow_signals scores; "
                f"expected {expected_score}, got {self.flow_score_ex_bb}"
            )
        if self.bandar_broad_score is not None and not (-12 <= self.bandar_broad_score <= 12):
            raise ValueError(
                f"FlowConfirmationEvidence bandar_broad_score must be -12 to +12, "
                f"got {self.bandar_broad_score}"
            )
        if not isinstance(self.bandar_direction, Direction):
            raise ValueError(f"bandar_direction must be Direction enum, got {self.bandar_direction!r}")
        if not isinstance(self.bandar_freshness, Freshness):
            raise ValueError(f"bandar_freshness must be Freshness enum, got {self.bandar_freshness!r}")
        if not isinstance(self.group_freshness, Freshness):
            raise ValueError(f"group_freshness must be Freshness enum, got {self.group_freshness!r}")

    @property
    def component_coverage(self) -> float:
        enabled_weight = sum(signal.weight for signal in self.flow_signals)
        if enabled_weight <= 0:
            return 0.0
        available_weight = sum(
            signal.weight
            for signal in self.flow_signals
            if signal.freshness is not Freshness.MISSING
        )
        return min(1.0, available_weight / enabled_weight)

    @property
    def missing_components(self) -> tuple[str, ...]:
        return tuple(
            signal.key
            for signal in self.flow_signals
            if signal.freshness is Freshness.MISSING
        )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "flow_signals": [s.to_dict() for s in self.flow_signals],
            "flow_score_ex_bb": self.flow_score_ex_bb,
            "confirmation_status": self.confirmation_status,
            "flow_direction": self.flow_direction,
            "bandar_broad_score": self.bandar_broad_score,
            "bandar_direction": self.bandar_direction.value,
            "bandar_freshness": self.bandar_freshness.value,
            "bci_label": self.bci_label,
            "bci_tier1_count": self.bci_tier1_count,
            "uncapped_strength": round(self.uncapped_strength, 4),
            "capped_strength": round(self.capped_strength, 4),
            "group_cap": self.group_cap,
            "group_freshness": self.group_freshness.value,
            "component_coverage": round(self.component_coverage, 4),
            "component_coverage_unit": "ratio_0_1",
            "missing_components": list(self.missing_components),
        }
