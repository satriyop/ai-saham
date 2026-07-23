"""
Pure DTOs for swing workflow calibration config.

Layer: Application (DTO)
"""

from dataclasses import dataclass, field
from decimal import Decimal

from src.application.services.setup_phase_config import SetupPhaseConfig


@dataclass(frozen=True)
class SetupTargetConfig:
    take_profit_pct: Decimal = Decimal("5")
    stop_loss_pct: Decimal = Decimal("5")


@dataclass(frozen=True)
class SwingConfig:
    """Swing workflow calibration params. All fields carry hardcoded defaults so
    the system works even when optional YAML policy files are absent or malformed."""

    # broker quality
    smart_money_brokers: tuple[str, ...] = ("AK", "BK", "KZ", "ZP", "RX", "MS", "DB", "ML", "YU")
    noise_brokers: tuple[str, ...] = ("YP", "PD", "XL", "XC")
    smart_weight: Decimal = Decimal("1.5")
    noise_weight: Decimal = Decimal("0.5")
    smart_share_threshold_pct: float = 60.0
    smart_sell_min_share_pct: float = 15.0
    # foreign_bounce setup gates
    foreign_bounce_enabled: bool = True
    gate_min_accum_score: float = 58.3
    gate_min_vwap_discount_pct: float = 3.0
    gate_required_trend: str = "SIDE"
    gate_min_flow_ratio_pct: float = 5.0
    gate_max_rsi: float = 60.0
    partial_max_failed_gates: int = 2
    # foreign_bounce entry authority (explicit config; no name-guessing — see
    # DecisionPolicyService). Backward-compat defaults only; current YAML is explicit.
    foreign_bounce_family: str = "unknown"
    foreign_bounce_entry_authority: bool = True
    foreign_bounce_can_enter_from_phases: tuple[str, ...] = ()
    # coiled_spring setup gates
    coiled_spring_enabled: bool = True
    coiled_spring_gate_min_accum_score: float = 50.0
    coiled_spring_gate_max_bb_width_pctile: float = 0.20
    coiled_spring_gate_min_flow_ratio_pct: float = 3.0
    coiled_spring_gate_max_rsi: float = 65.0
    coiled_spring_partial_max_failed_gates: int = 2
    coiled_spring_family: str = "unknown"
    coiled_spring_entry_authority: bool = True
    coiled_spring_can_enter_from_phases: tuple[str, ...] = ()
    # smart_money_confirmed setup gates
    smart_money_confirmed_enabled: bool = True
    smart_money_confirmed_gate_min_accum_score: float = 50.0
    smart_money_confirmed_gate_min_smart_flow_idr: Decimal = Decimal("0")
    smart_money_confirmed_gate_min_smart_share_pct: float = 30.0
    smart_money_confirmed_gate_max_noise_share_pct: float = 60.0
    smart_money_confirmed_reject_smart_net_selling: bool = True
    smart_money_confirmed_partial_max_failed_gates: int = 1
    smart_money_confirmed_family: str = "unknown"
    smart_money_confirmed_entry_authority: bool = True
    smart_money_confirmed_can_enter_from_phases: tuple[str, ...] = ()
    # pullback_continuation setup gates
    pullback_continuation_enabled: bool = True
    pullback_continuation_gate_min_accum_score: float = 45.8
    pullback_continuation_gate_required_trend: str = "UP"
    pullback_continuation_gate_min_flow_ratio_pct: float = 2.0
    pullback_continuation_gate_min_rsi: float = 40.0
    pullback_continuation_gate_max_rsi: float = 65.0
    pullback_continuation_gate_min_vwap_discount_pct: float = -2.0
    pullback_continuation_partial_max_failed_gates: int = 2
    pullback_continuation_family: str = "unknown"
    pullback_continuation_entry_authority: bool = True
    pullback_continuation_can_enter_from_phases: tuple[str, ...] = ()
    # verdict + signal label thresholds
    enter_min_score: float = 58.3
    watch_min_score: float = 33.3
    strong_min_score: float = 58.3
    strong_min_streak: int = 8
    building_min_score: float = 50.0
    building_min_streak: int = 5
    coiled_spring_bb_pctile: float = 0.20
    coiled_spring_min_score: float = 50.0
    # screener: market cap floor (0 = disabled; e.g. 500_000_000_000 = 500B IDR)
    min_market_cap_idr: int = 0
    # tier1 broker codes for BCI (Broker Concentration Index) scoring
    tier1_broker_codes: frozenset[str] = frozenset(
        {"AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR"}
    )
    bci_cluster_min_count: int = 3
    bci_stable_min_count: int = 1
    # regime-adaptive setup exits
    setup_targets: dict[str, SetupTargetConfig] = field(default_factory=lambda: {
        "risk_on": SetupTargetConfig(Decimal("8"), Decimal("4")),
        "neutral": SetupTargetConfig(Decimal("5"), Decimal("5")),
        "volatile": SetupTargetConfig(Decimal("3"), Decimal("3")),
        "risk_off": SetupTargetConfig(Decimal("3"), Decimal("3")),
        "default": SetupTargetConfig(Decimal("5"), Decimal("5")),
    })
    # sector breadth confirmation (accumulation_screener.yaml)
    sector_breadth_enabled: bool = True
    sector_breadth_threshold: float = 0.60
    sector_breadth_bonus_pts: float = 10.0
    sector_breadth_min_tickers: int = 3
    # resistance/corporate-action gates
    resistance_gate_enabled: bool = True
    resistance_headroom_min_pct: float = 5.0
    ex_date_warning_days: int = 10
    setup_phase_config: SetupPhaseConfig = field(default_factory=SetupPhaseConfig)
