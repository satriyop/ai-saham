"""
Signal engine scoring config resolving.

Pure config normalization that composes the full SignalEngineConfig from a
raw signal_engine.yaml dict: classification, scoring sub-sections, input
mapping, enrichment, evidence groups, flags, regime conditioning, decision
policy, and alpha/trigger config. No engine construction, no infrastructure
wiring.

`signal_engine.factors` and `signal_engine.missing_data` are removed legacy
keys (RETIRE-LEGACY-SIX-FACTOR-BASELINE Slice 2), and
`signal_engine.scoring.seasonality/analyst/forward_pe` are removed
non-operational keys (Slice 2 findings fix — no producer ever read them from
YAML; the diagnostic company-quality producer uses typed SignalScoringConfig()
defaults). All are rejected explicitly rather than silently ignored, so stale
config cannot appear to configure canonical or diagnostic scoring.
"""

from __future__ import annotations

from src.application.services.engine_bootstrap.signal_alpha_trigger_config_resolver import (
    resolve_alpha_trigger_config,
)
from src.application.services.engine_bootstrap.signal_decision_policy_config_resolver import (
    resolve_decision_policy_config,
)
from src.application.services.signal_engine_config import (
    AccumScoreMappingConfig,
    AlphaTriggerConfig,
    AnalystBearishFlagConfig,
    BandarScoringConfig,
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    InsiderSellingFlagConfig,
    NeutralRegimeConfig,
    PreOpenDirectionalBaselineConfig,
    RegimeConditioningConfig,
    RiskOffRegimeConfig,
    SignalClassificationConfig,
    SignalEngineConfig,
    SignalEnrichmentConfig,
    SignalFlagsConfig,
    SignalInputMappingConfig,
    SignalScoringConfig,
    ValuationStretchedFlagConfig,
    VolatileRegimeConfig,
)


def _validate_evidence_group_config(
    name: str,
    group: EvidenceGroupConfig,
    alpha_trigger_cfg: AlphaTriggerConfig,
) -> None:
    """HIGH-2: fail closed on malformed evidence-group config at load time —
    a misspelled or missing authority_registration must never silently
    resolve as diagnostic in production config."""
    if group.weight <= 0:
        raise ValueError(
            f"signal_engine.evidence_groups.{name}.weight must be > 0, got {group.weight!r}"
        )
    if not group.authority_registration:
        raise ValueError(
            f"signal_engine.evidence_groups.{name}.authority_registration cannot be empty"
        )
    if group.authority_registration not in alpha_trigger_cfg.evidence_registrations:
        raise ValueError(
            f"signal_engine.evidence_groups.{name}.authority_registration="
            f"{group.authority_registration!r} does not exist in "
            "signal_engine.alpha_trigger.evidence_registrations"
        )
    if not isinstance(group.required_for_authority, bool):
        raise ValueError(
            f"signal_engine.evidence_groups.{name}.required_for_authority must be "
            f"a boolean, got {group.required_for_authority!r}"
        )


def resolve_signal_engine_config(cfg: dict) -> SignalEngineConfig:
    root = cfg.get("signal_engine", {})
    if "factors" in root:
        raise ValueError(
            "signal_engine.factors was removed (RETIRE-LEGACY-SIX-FACTOR-BASELINE) "
            "and does not configure canonical scoring. Delete it from config."
        )
    if "missing_data" in root:
        raise ValueError(
            "signal_engine.missing_data was removed (RETIRE-LEGACY-SIX-FACTOR-BASELINE) "
            "and does not configure canonical scoring. Delete it from config."
        )
    classification = root.get("classification", {})
    scoring = root.get("scoring", {})
    _REMOVED_SCORING_CONFIG_CLASS = {
        "seasonality": "SeasonalityScoringConfig",
        "analyst": "AnalystScoringConfig",
        "forward_pe": "ForwardPeScoringConfig",
    }
    for removed_scoring_key, config_class in _REMOVED_SCORING_CONFIG_CLASS.items():
        if removed_scoring_key in scoring:
            raise ValueError(
                f"signal_engine.scoring.{removed_scoring_key} was removed "
                "(non-operational — never read by any production or diagnostic "
                "YAML path). The diagnostic company-quality producer "
                f"(CompanyQualityContextEvidenceBuilder) uses typed {config_class}() "
                "defaults, not YAML-resolved scoring. Delete it from config."
            )
    enrichment = root.get("enrichment", {})
    input_mapping = root.get("input_mapping", {})
    if "foreign_flow_score" in input_mapping:
        raise ValueError(
            "signal_engine.input_mapping.foreign_flow_score was renamed to "
            "input_mapping.accum_score (ADR-043). Update config/signal_engine.yaml."
        )
    accum_score_mapping = input_mapping.get("accum_score", {})
    bandar = scoring.get("bandar", {})
    evidence_groups = root.get("evidence_groups", {})
    flags = root.get("flags", {})
    flag_valuation = flags.get("valuation_stretched", {})
    flag_analyst = flags.get("analyst_bearish", {})
    flag_insider = flags.get("insider_selling", {})
    regime_cfg = root.get("regime_conditioning", {})
    rc_neutral = regime_cfg.get("neutral", {})
    rc_risk_off = regime_cfg.get("risk_off", {})
    rc_volatile = regime_cfg.get("volatile", {})
    decision_cfg = root.get("decision_policy", {})
    decision_policy = resolve_decision_policy_config(decision_cfg)
    alpha_trigger_cfg = resolve_alpha_trigger_config(root.get("alpha_trigger", {}))
    pre_open = root.get("pre_open_directional_baseline", {})

    setup_quality_group = EvidenceGroupConfig(
        weight=evidence_groups.get("setup_quality", {}).get("weight", 0.60),
        authority_registration=evidence_groups.get("setup_quality", {}).get(
            "authority_registration", "setup_quality"
        ),
        required_for_authority=evidence_groups.get("setup_quality", {}).get(
            "required_for_authority", True
        ),
    )
    flow_confirmation_group = EvidenceGroupConfig(
        weight=evidence_groups.get("flow_confirmation", {}).get("weight", 0.40),
        authority_registration=evidence_groups.get("flow_confirmation", {}).get(
            "authority_registration", "institutional_flow"
        ),
        required_for_authority=evidence_groups.get("flow_confirmation", {}).get(
            "required_for_authority", True
        ),
    )
    _validate_evidence_group_config("setup_quality", setup_quality_group, alpha_trigger_cfg)
    _validate_evidence_group_config("flow_confirmation", flow_confirmation_group, alpha_trigger_cfg)

    return SignalEngineConfig(
        classification=SignalClassificationConfig(
            strong_min_score=classification.get("strong_min_score", 70),
            moderate_min_score=classification.get("moderate_min_score", 45),
        ),
        # seasonality/analyst/forward_pe sub-configs are intentionally omitted:
        # they are non-operational YAML keys (rejected above if present).
        # CompanyQualityContextEvidenceBuilder uses their typed dataclass
        # defaults directly, not YAML-resolved scoring.
        scoring=SignalScoringConfig(
            bandar=BandarScoringConfig(
                mandatory_signal_count=bandar.get("mandatory_signal_count", 3),
                signal_score_unit=bandar.get("signal_score_unit", 2),
                default_max_range=bandar.get("default_max_range", 6),
            ),
        ),
        input_mapping=SignalInputMappingConfig(
            accum_score=AccumScoreMappingConfig(
                max_score=accum_score_mapping.get("max_score", 100.0),
                clamp=accum_score_mapping.get("clamp", True),
            ),
        ),
        enrichment=SignalEnrichmentConfig(
            insider_lookback_days=enrichment.get("insider_lookback_days", 90),
        ),
        evidence_groups=EvidenceGroupsConfig(
            setup_quality=setup_quality_group,
            flow_confirmation=flow_confirmation_group,
        ),
        flags=SignalFlagsConfig(
            valuation_stretched=ValuationStretchedFlagConfig(
                enabled=flag_valuation.get("enabled", True),
                forward_pe_threshold=flag_valuation.get("forward_pe_threshold", 50.0),
                score_penalty=int(flag_valuation.get("score_penalty", 10)),
            ),
            analyst_bearish=AnalystBearishFlagConfig(
                enabled=flag_analyst.get("enabled", True),
                buy_ratio_threshold=flag_analyst.get("buy_ratio_threshold", 0.20),
                score_penalty=int(flag_analyst.get("score_penalty", 8)),
            ),
            insider_selling=InsiderSellingFlagConfig(
                enabled=flag_insider.get("enabled", True),
                net_buy_ratio_threshold=flag_insider.get("net_buy_ratio_threshold", -0.30),
                score_penalty=int(flag_insider.get("score_penalty", 12)),
            ),
        ),
        regime_conditioning=RegimeConditioningConfig(
            neutral=NeutralRegimeConfig(
                weak_flow_threshold=rc_neutral.get("weak_flow_threshold", 50.0),
                weak_flow_discount=rc_neutral.get("weak_flow_discount", 0.80),
            ),
            risk_off=RiskOffRegimeConfig(
                weak_setup_threshold=rc_risk_off.get("weak_setup_threshold", 60.0),
                weak_setup_discount=rc_risk_off.get("weak_setup_discount", 0.50),
            ),
            volatile=VolatileRegimeConfig(
                setup_discount=rc_volatile.get("setup_discount", 0.70),
                flow_discount=rc_volatile.get("flow_discount", 0.80),
            ),
        ),
        decision_policy=decision_policy,
        alpha_trigger=alpha_trigger_cfg,
        pre_open_directional_baseline=PreOpenDirectionalBaselineConfig(
            contract=str(pre_open.get("contract", "pre_open_directional_baseline.v1")),
            buy_pressure_min=float(pre_open.get("buy_pressure_min", 0.60)),
            sell_pressure_max=float(pre_open.get("sell_pressure_max", 0.40)),
            high_confidence_build_min=float(pre_open.get("high_confidence_build_min", 0.08)),
            medium_confidence_floor=float(pre_open.get("medium_confidence_floor", -0.03)),
            min_normalized_iev_intensity=float(pre_open.get("min_normalized_iev_intensity", 1.0)),
            reliable_spread_max_pct=float(pre_open.get("reliable_spread_max_pct", 1.0)),
            max_spread_pct=float(pre_open.get("max_spread_pct", 1.5)),
            large_gap_caution_pct=float(pre_open.get("large_gap_caution_pct", 5.0)),
            bullish_high_score=int(pre_open.get("bullish_high_score", 80)),
            bullish_medium_score=int(pre_open.get("bullish_medium_score", 70)),
            bullish_low_score=int(pre_open.get("bullish_low_score", 55)),
            neutral_score=int(pre_open.get("neutral_score", 45)),
            conflicted_score=int(pre_open.get("conflicted_score", 35)),
            bearish_score=int(pre_open.get("bearish_score", 20)),
            unknown_score=int(pre_open.get("unknown_score", 0)),
        ),
    )
