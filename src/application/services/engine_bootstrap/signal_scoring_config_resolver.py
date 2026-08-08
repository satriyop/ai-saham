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
defaults). `signal_engine.evidence_groups.setup_quality` is a retired evidence
group (ADR-067): `flow_confirmation` is the sole production group and the
signal score is the flow group score, so a declared setup weight configures
nothing. All are rejected explicitly rather than silently ignored, so stale
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
    rc_volatile = regime_cfg.get("volatile", {})
    decision_cfg = root.get("decision_policy", {})
    decision_policy = resolve_decision_policy_config(decision_cfg)
    alpha_trigger_cfg = resolve_alpha_trigger_config(root.get("alpha_trigger", {}))
    pre_open = root.get("pre_open_directional_baseline", {})

    if "setup_quality" in evidence_groups:
        raise ValueError(
            "signal_engine.evidence_groups.setup_quality was retired (ADR-067). "
            "It was present in 0 of 7,764 accum window-observations, so its "
            "declared weight configured nothing the screen produced. "
            "flow_confirmation is the sole production evidence group and the "
            "signal score is the flow group score. Delete it from config; "
            "there is no compatibility path."
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
            volatile=VolatileRegimeConfig(
                flow_discount=rc_volatile.get("flow_discount", 0.80),
            ),
        ),
        decision_policy=decision_policy,
        alpha_trigger=alpha_trigger_cfg,
        pre_open_directional_baseline=PreOpenDirectionalBaselineConfig(
            contract=str(pre_open.get("contract", "pre_open_directional_baseline.v2")),
            buy_pressure_min=float(pre_open.get("buy_pressure_min", 0.60)),
            sell_pressure_max=float(pre_open.get("sell_pressure_max", 0.40)),
            high_confidence_build_min=float(pre_open.get("high_confidence_build_min", 0.08)),
            medium_confidence_floor=float(pre_open.get("medium_confidence_floor", -0.03)),
            intensity_high_soft=float(pre_open.get("intensity_high_soft", 0.02)),
            reliable_spread_max_pct=float(pre_open.get("reliable_spread_max_pct", 1.0)),
            max_spread_pct=float(pre_open.get("max_spread_pct", 1.5)),
            large_gap_caution_pct=float(pre_open.get("large_gap_caution_pct", 5.0)),
            rsi_extension_threshold=float(pre_open.get("rsi_extension_threshold", 75.0)),
            anchor_bullish=float(pre_open.get("anchor_bullish", 58.0)),
            anchor_neutral=float(pre_open.get("anchor_neutral", 45.0)),
            anchor_conflicted=float(pre_open.get("anchor_conflicted", 35.0)),
            anchor_bearish=float(pre_open.get("anchor_bearish", 22.0)),
            weight_pressure=float(pre_open.get("weight_pressure", 18.0)),
            weight_delta=float(pre_open.get("weight_delta", 22.0)),
            weight_intensity=float(pre_open.get("weight_intensity", 12.0)),
            intensity_scale=float(pre_open.get("intensity_scale", 0.02)),
            delta_clamp=float(pre_open.get("delta_clamp", 0.35)),
            enter_min_score=float(pre_open.get("enter_min_score", 62.0)),
            watch_min_score=float(pre_open.get("watch_min_score", 48.0)),
        ),
    )
