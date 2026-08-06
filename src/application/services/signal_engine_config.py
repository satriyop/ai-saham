"""
Signal Engine Configuration — all frozen dataclasses for signal scoring.

This module consolidates every config type used by the signal engine:
- Factor scoring config (shared with company_quality_scoring)
- Signal engine config (classification, input mapping, etc.)
- Evidence group weights
- Risk flag configs
- Regime conditioning configs
- Decision policy configs
- Alpha trigger configs

Layer: Application (configuration only). Depends on stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.services.signal_scoring_config import (
    AnalystScoringConfig,
    BandarScoringConfig,
    ForwardPeScoringConfig,
    SeasonalityScoringConfig,
    SignalScoringConfig,
)
from src.domain.value_objects.alpha_trigger_score import (
    REMOVED_MARKET_CONTEXT_EVIDENCE_NAME,
    SECTOR_CONTEXT_EVIDENCE_NAME,
    EvidenceAuthorityStatus,
    EvidenceRegistration,
)

_REMOVED_GROUP_MESSAGE = (
    f"Alpha/Trigger group {REMOVED_MARKET_CONTEXT_EVIDENCE_NAME!r} was removed; "
    f"use {SECTOR_CONTEXT_EVIDENCE_NAME!r}"
)

# ── Phase 1: classification & missing-data config ──────────────────────────────


@dataclass(frozen=True)
class SignalClassificationConfig:
    strong_min_score: int = 70
    moderate_min_score: int = 45


@dataclass(frozen=True)
class PreOpenDirectionalBaselineConfig:
    contract: str = "pre_open_directional_baseline.v1"
    buy_pressure_min: float = 0.60
    sell_pressure_max: float = 0.40
    high_confidence_build_min: float = 0.08
    medium_confidence_floor: float = -0.03
    min_normalized_iev_intensity: float = 1.0
    reliable_spread_max_pct: float = 1.0
    max_spread_pct: float = 1.5
    large_gap_caution_pct: float = 5.0
    rsi_extension_threshold: float = 75.0
    bullish_high_score: int = 80
    bullish_medium_score: int = 70
    bullish_low_score: int = 55
    neutral_score: int = 45
    conflicted_score: int = 35
    bearish_score: int = 20
    unknown_score: int = 0

    def __post_init__(self) -> None:
        if self.contract != "pre_open_directional_baseline.v1":
            raise ValueError("unsupported pre-open directional baseline contract")
        if not 0.0 <= self.sell_pressure_max < self.buy_pressure_min <= 1.0:
            raise ValueError("pre-open book pressure thresholds must be ordered")
        if self.max_spread_pct < self.reliable_spread_max_pct:
            raise ValueError("max spread must be >= reliable spread")
        scores = (
            self.bullish_high_score,
            self.bullish_medium_score,
            self.bullish_low_score,
            self.neutral_score,
            self.conflicted_score,
            self.bearish_score,
            self.unknown_score,
        )
        if any(not 0 <= score <= 100 for score in scores):
            raise ValueError("pre-open baseline scores must be 0-100")


# ── Phase 2: input mapping config ──────────────────────────────────────────────


@dataclass(frozen=True)
class AccumScoreMappingConfig:
    max_score: float = 100.0
    clamp: bool = True


@dataclass(frozen=True)
class SignalInputMappingConfig:
    accum_score: AccumScoreMappingConfig = field(default_factory=AccumScoreMappingConfig)


# ── Phase 3: enrichment config ─────────────────────────────────────────────────


@dataclass(frozen=True)
class SignalEnrichmentConfig:
    insider_lookback_days: int = 90


# ── Phase 4: evidence-group and flag config ─────────────────────────────────────


@dataclass(frozen=True)
class EvidenceGroupConfig:
    weight: float = 1.0
    # Key into alpha_trigger.evidence_registrations — the sole central
    # authority-status source (HIGH-2). Do not duplicate authority status here.
    authority_registration: str = ""
    required_for_authority: bool = True


@dataclass(frozen=True)
class EvidenceGroupsConfig:
    """The production evidence basis for canonical signal scoring.

    ADR-067 retired `setup_quality`, leaving exactly one group. There is no
    blend and no renormalization: the signal score IS the flow group score.
    `weight` survives as the declared production basis (ADR-059 policy
    snapshot material), not as a divisor.
    """

    flow_confirmation: EvidenceGroupConfig = field(
        default_factory=lambda: EvidenceGroupConfig(
            weight=0.40,
            authority_registration="institutional_flow",
            required_for_authority=True,
        )
    )


@dataclass(frozen=True)
class ValuationStretchedFlagConfig:
    enabled: bool = True
    forward_pe_threshold: float = 50.0
    score_penalty: int = 10


@dataclass(frozen=True)
class AnalystBearishFlagConfig:
    enabled: bool = True
    buy_ratio_threshold: float = 0.20
    score_penalty: int = 8


@dataclass(frozen=True)
class InsiderSellingFlagConfig:
    enabled: bool = True
    net_buy_ratio_threshold: float = -0.30
    score_penalty: int = 12


@dataclass(frozen=True)
class SignalFlagsConfig:
    valuation_stretched: ValuationStretchedFlagConfig = field(
        default_factory=ValuationStretchedFlagConfig
    )
    analyst_bearish: AnalystBearishFlagConfig = field(default_factory=AnalystBearishFlagConfig)
    insider_selling: InsiderSellingFlagConfig = field(default_factory=InsiderSellingFlagConfig)


# ── Phase 5: regime-conditional group score conditioning ────────────────────────


@dataclass(frozen=True)
class NeutralRegimeConfig:
    """NEUTRAL regime: discount weak flow confirmation below threshold."""

    weak_flow_threshold: float = 50.0
    weak_flow_discount: float = 0.80


@dataclass(frozen=True)
class VolatileRegimeConfig:
    """VOLATILE regime: discount flow confirmation."""

    flow_discount: float = 0.80


@dataclass(frozen=True)
class RegimeConditioningConfig:
    """Per-regime group score conditioning applied before renormalization.

    RISK_ON:  no conditioning (normal confidence).
    NEUTRAL:  weak flow discounted (market needs stronger flow confirmation).
    RISK_OFF: no conditioning. Its only branch discounted setup evidence, which
              ADR-067 retired as an evidence group; the whole RISK_OFF config
              (weak_setup_threshold / weak_setup_discount) went with it.
    VOLATILE: flow discounted (higher bar in fast-moving markets). Its setup
              half was removed with RISK_OFF's, for the same reason.
    """

    neutral: NeutralRegimeConfig = field(default_factory=NeutralRegimeConfig)
    volatile: VolatileRegimeConfig = field(default_factory=VolatileRegimeConfig)


# ── Decision Policy Config ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class RegimeDecisionPolicyConfig:
    enter_allowed: bool = True
    max_decision: str = "ENTER"
    regime_size_multiplier: float = 1.0
    enter_threshold: int | None = None
    watch_threshold: int = 45
    # HIGH-2: canonical production-authority coverage floor. Replaces the
    # ambiguous min_coverage/min_conviction dual gate — numeric values are
    # preserved from the former min_coverage, not recalibrated.
    min_signal_authority_coverage: float = 0.0


@dataclass(frozen=True)
class SetupRegimeActionConfig:
    max_decision: str = "ENTER"


@dataclass(frozen=True)
class DecisionPolicyConfig:
    regime_policy: dict[str, RegimeDecisionPolicyConfig] = field(
        default_factory=lambda: {
            "RISK_ON": RegimeDecisionPolicyConfig(
                enter_allowed=True,
                max_decision="ENTER",
                regime_size_multiplier=1.0,
                enter_threshold=70,
                watch_threshold=45,
                min_signal_authority_coverage=0.70,
            ),
            "NEUTRAL": RegimeDecisionPolicyConfig(
                enter_allowed=True,
                max_decision="ENTER",
                regime_size_multiplier=0.50,
                enter_threshold=72,
                watch_threshold=45,
                min_signal_authority_coverage=0.70,
            ),
            "RISK_OFF": RegimeDecisionPolicyConfig(
                enter_allowed=False,
                max_decision="WATCH",
                regime_size_multiplier=0.25,
                enter_threshold=None,
                watch_threshold=60,
                min_signal_authority_coverage=0.80,
            ),
            "VOLATILE": RegimeDecisionPolicyConfig(
                enter_allowed=False,
                max_decision="WATCH",
                regime_size_multiplier=0.0,
                enter_threshold=None,
                watch_threshold=65,
                min_signal_authority_coverage=1.0,
            ),
        }
    )
    setup_regime_policy: dict[str, dict[str, str]] = field(default_factory=dict)
    setup_regime_actions: dict[str, SetupRegimeActionConfig] = field(
        default_factory=lambda: {
            "allowed": SetupRegimeActionConfig(max_decision="ENTER"),
            "restricted_or_watch_only": SetupRegimeActionConfig(max_decision="WATCH"),
            "enter_disabled": SetupRegimeActionConfig(max_decision="WATCH"),
            "allowed_if_flow_confirmation_strong": SetupRegimeActionConfig(max_decision="ENTER"),
        }
    )
    # A2: caps applied when regime quality metadata is available
    regime_confidence_min_enter: float = 0.35  # cap ENTER→WATCH when confidence < this
    regime_transitioning_cap_enter: bool = True  # cap ENTER→WATCH when stability == TRANSITIONING


# ── Alpha Trigger Config ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlphaTriggerRouteFractionsConfig:
    """Per-horizon group routing fractions. Trigger fraction is always derived."""

    by_horizon: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "TACTICAL_3D": {
                "setup_quality": 0.00,
                "institutional_flow": 0.70,
                SECTOR_CONTEXT_EVIDENCE_NAME: 0.25,
                "company_quality_context": 1.00,
            },
            "SWING_10D": {
                "setup_quality": 0.00,
                "institutional_flow": 0.80,
                SECTOR_CONTEXT_EVIDENCE_NAME: 0.60,
                "company_quality_context": 1.00,
            },
            "ACCUM_20D": {
                "setup_quality": 0.10,
                "institutional_flow": 0.90,
                SECTOR_CONTEXT_EVIDENCE_NAME: 0.75,
                "company_quality_context": 1.00,
            },
        }
    )


@dataclass(frozen=True)
class AlphaTriggerConfig:
    enabled: bool = True
    default_horizon: str = "SWING_10D"
    group_weights: dict[str, float] = field(
        default_factory=lambda: {
            "setup_quality": 0.35,
            "institutional_flow": 0.30,
            SECTOR_CONTEXT_EVIDENCE_NAME: 0.25,
            "company_quality_context": 0.10,
        }
    )
    route_fractions: dict[str, dict[str, float]] = field(
        default_factory=lambda: AlphaTriggerRouteFractionsConfig().by_horizon
    )
    horizon_alpha_weights: dict[str, float] = field(
        default_factory=lambda: {
            "TACTICAL_3D": 0.20,
            "SWING_10D": 0.40,
            "ACCUM_20D": 0.50,
        }
    )
    low_weight_cap: float = 0.10
    evidence_registrations: dict[str, EvidenceRegistration] = field(
        default_factory=lambda: {
            "setup_quality": EvidenceRegistration(
                evidence_name="setup_quality",
                status=EvidenceAuthorityStatus.PRODUCTION,
            ),
            "institutional_flow": EvidenceRegistration(
                evidence_name="institutional_flow",
                status=EvidenceAuthorityStatus.PRODUCTION,
            ),
            SECTOR_CONTEXT_EVIDENCE_NAME: EvidenceRegistration(
                evidence_name=SECTOR_CONTEXT_EVIDENCE_NAME,
                status=EvidenceAuthorityStatus.DIAGNOSTIC,
            ),
            "company_quality_context": EvidenceRegistration(
                evidence_name="company_quality_context",
                status=EvidenceAuthorityStatus.DIAGNOSTIC,
            ),
        }
    )

    def __post_init__(self) -> None:
        """Fail closed against the removed Alpha/Trigger group identity even
        under direct typed construction (manual DI), not only YAML resolving
        (SECTOR-CONTEXT-IDENTITY). market_context is removed from the
        Alpha/Trigger namespace; its producer is SectorContextEvidence, which
        registers under sector_context. This is a rejection guard, not an
        alias — the removed key is never translated to the canonical name."""
        if REMOVED_MARKET_CONTEXT_EVIDENCE_NAME in self.group_weights:
            raise ValueError(
                "AlphaTriggerConfig.group_weights."
                f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME}: {_REMOVED_GROUP_MESSAGE}"
            )
        for horizon, groups in self.route_fractions.items():
            if REMOVED_MARKET_CONTEXT_EVIDENCE_NAME in groups:
                raise ValueError(
                    f"AlphaTriggerConfig.route_fractions.{horizon}."
                    f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME}: {_REMOVED_GROUP_MESSAGE}"
                )
        if REMOVED_MARKET_CONTEXT_EVIDENCE_NAME in self.evidence_registrations:
            raise ValueError(
                "AlphaTriggerConfig.evidence_registrations."
                f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME}: {_REMOVED_GROUP_MESSAGE}"
            )
        for key, registration in self.evidence_registrations.items():
            if key != registration.evidence_name:
                raise ValueError(
                    f"AlphaTriggerConfig.evidence_registrations.{key}: "
                    f"registration key {key!r} must equal "
                    f"registration.evidence_name {registration.evidence_name!r}"
                )


# ── Aggregated Engine Config ────────────────────────────────────────────────────


@dataclass(frozen=True)
class SignalEngineConfig:
    classification: SignalClassificationConfig = field(default_factory=SignalClassificationConfig)
    scoring: SignalScoringConfig = field(default_factory=SignalScoringConfig)
    input_mapping: SignalInputMappingConfig = field(default_factory=SignalInputMappingConfig)
    enrichment: SignalEnrichmentConfig = field(default_factory=SignalEnrichmentConfig)
    evidence_groups: EvidenceGroupsConfig = field(default_factory=EvidenceGroupsConfig)
    flags: SignalFlagsConfig = field(default_factory=SignalFlagsConfig)
    regime_conditioning: RegimeConditioningConfig = field(default_factory=RegimeConditioningConfig)
    decision_policy: DecisionPolicyConfig = field(default_factory=DecisionPolicyConfig)
    alpha_trigger: AlphaTriggerConfig = field(default_factory=AlphaTriggerConfig)
    pre_open_directional_baseline: PreOpenDirectionalBaselineConfig = field(
        default_factory=PreOpenDirectionalBaselineConfig
    )


# Re-export shared scoring configs for backward-compatible imports
__all__ = [
    # Shared scoring configs (from signal_scoring_config)
    "SignalScoringConfig",
    "BandarScoringConfig",
    "SeasonalityScoringConfig",
    "AnalystScoringConfig",
    "ForwardPeScoringConfig",
    # New configs
    "SignalClassificationConfig",
    "PreOpenDirectionalBaselineConfig",
    "AccumScoreMappingConfig",
    "SignalInputMappingConfig",
    "SignalEnrichmentConfig",
    "EvidenceGroupConfig",
    "EvidenceGroupsConfig",
    "ValuationStretchedFlagConfig",
    "AnalystBearishFlagConfig",
    "InsiderSellingFlagConfig",
    "SignalFlagsConfig",
    "NeutralRegimeConfig",
    "VolatileRegimeConfig",
    "RegimeConditioningConfig",
    "RegimeDecisionPolicyConfig",
    "SetupRegimeActionConfig",
    "DecisionPolicyConfig",
    "AlphaTriggerRouteFractionsConfig",
    "AlphaTriggerConfig",
    "SignalEngineConfig",
]
