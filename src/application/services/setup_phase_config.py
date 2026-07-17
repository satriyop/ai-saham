"""Setup phase configuration dataclasses.

Layer: Application
Depends on: domain value objects + stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.value_objects.setup_phase import SetupPhaseState


@dataclass(frozen=True)
class SetupPhaseThresholdsConfig:
    # Rescaled 0-120 -> 0-100 (ADR-039). NOT currently read by
    # _constructive_phase()'s accumulation gate (uses passed_gates/flow_status
    # instead) — kept for potential future wiring, not an active lever.
    accumulation_min_flow_score: float = 50.0
    accumulation_min_flow_ratio_pct: float = 2.0
    compression_max_bb_width_pctile: float = 0.20
    breakout_min_close_above_prev_high_pct: float = 0.0
    # Superseded by volume_trigger.dry_up_max_ratio / expansion_min_ratio
    # (Point 3, explicit dry-up + expansion evidence). Kept for backward
    # compatibility with existing config/tuning-bounds entries; no longer an
    # active lever in _constructive_phase().
    breakout_min_volume_ratio: float = 1.2
    breakout_reclaim_vwap_min_pct: float = 0.0
    exhaustion_rsi_min: float = 72.0
    exhaustion_min_price_extension_pct: float = 8.0
    distribution_min_bandar_score: int = -4
    failed_max_drawdown_from_recent_high_pct: float = -7.0
    failed_breakdown_below_support_pct: float = -3.0


@dataclass(frozen=True)
class VolumeTriggerValidityConfig:
    require_trusted_volume: bool = True
    trusted_benchmark_volume_sources: tuple[str, ...] = ("stockbit", "idx")
    min_valid_20d_sessions: int = 18
    zero_volume_tolerance: int = 1
    # Explicit dry-up/expansion evidence (Point 3). Requires
    # dry_up_reference_sessions + 1 total candles: the latest session is a
    # standalone expansion candidate, dry_up_lookback_sessions immediately
    # before it form the dry-up window, and the remaining
    # (dry_up_reference_sessions - dry_up_lookback_sessions) sessions before
    # that form the reference/baseline window. dry_up_ratio = avg(dry-up
    # window) / avg(reference window). expansion_ratio = latest session
    # volume / avg(dry-up window).
    dry_up_lookback_sessions: int = 5
    dry_up_reference_sessions: int = 20
    dry_up_max_ratio: float = 0.50
    expansion_min_ratio: float = 1.50
    expansion_requires_positive_close: bool = True


@dataclass(frozen=True)
class VolumeTriggerEvidence:
    """Explicit dry-up/expansion evidence — replaces a single loose ratio.

    volume_trigger_confirmed is the ONLY flag that may justify claiming a
    genuine "dry-up then expansion" breakout trigger. dry_up_confirmed or
    expansion_confirmed alone are honest partial evidence, not a trigger.
    """

    dry_up_ratio: float | None
    expansion_ratio: float | None
    dry_up_confirmed: bool
    expansion_confirmed: bool
    volume_trigger_confirmed: bool
    data_valid: bool
    unavailable_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetupPhaseRequirementConfig:
    required_sequence: tuple[SetupPhaseState, ...] = ()
    enter_phases: tuple[SetupPhaseState, ...] = ()
    requires_reclaim_or_pivot: bool = False
    entry_authority: bool | None = None


_ACCUMULATION_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(
    required_sequence=(
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ),
    enter_phases=(SetupPhaseState.BREAKOUT_CONFIRMATION,),
)
_BREAKOUT_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(
    required_sequence=(
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ),
    enter_phases=(SetupPhaseState.BREAKOUT_CONFIRMATION,),
)
_PULLBACK_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(
    enter_phases=(SetupPhaseState.BREAKOUT_CONFIRMATION,),
    requires_reclaim_or_pivot=True,
)
_CONFIRMATION_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(entry_authority=False)


@dataclass(frozen=True)
class SetupPhaseConfig:
    thresholds: SetupPhaseThresholdsConfig = field(
        default_factory=SetupPhaseThresholdsConfig
    )
    requirements_by_family: dict[str, SetupPhaseRequirementConfig] = field(
        default_factory=lambda: {
            "accumulation": _ACCUMULATION_SEQUENCE_REQUIREMENT,
            "foreign-bounce": _ACCUMULATION_SEQUENCE_REQUIREMENT,
            "foreign_bounce": _ACCUMULATION_SEQUENCE_REQUIREMENT,
            "breakout": _BREAKOUT_SEQUENCE_REQUIREMENT,
            "coiled-spring": _BREAKOUT_SEQUENCE_REQUIREMENT,
            "coiled_spring": _BREAKOUT_SEQUENCE_REQUIREMENT,
            "pullback": _PULLBACK_SEQUENCE_REQUIREMENT,
            "pullback-continuation": _PULLBACK_SEQUENCE_REQUIREMENT,
            "pullback_continuation": _PULLBACK_SEQUENCE_REQUIREMENT,
            "confirmation": _CONFIRMATION_SEQUENCE_REQUIREMENT,
            "smart-money-confirmed": _CONFIRMATION_SEQUENCE_REQUIREMENT,
            "smart_money_confirmed": _CONFIRMATION_SEQUENCE_REQUIREMENT,
        }
    )
    volume_trigger: VolumeTriggerValidityConfig = field(
        default_factory=VolumeTriggerValidityConfig
    )

    def requirement_for(
        self, setup_family: str | None
    ) -> SetupPhaseRequirementConfig | None:
        if not setup_family:
            return None
        key = setup_family.strip().lower()
        return self.requirements_by_family.get(key) or self.requirements_by_family.get(
            key.replace("-", "_")
        )
