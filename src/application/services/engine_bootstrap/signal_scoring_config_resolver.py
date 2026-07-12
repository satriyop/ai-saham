"""
Signal engine scoring config resolving.

Pure config normalization that composes the full SignalEngineConfig from a
raw signal_engine.yaml dict: classification, missing-data handling, scoring
sub-sections, input mapping, enrichment, evidence groups, flags, regime
conditioning, decision policy, and alpha/trigger config. No engine
construction, no infrastructure wiring.
"""

from __future__ import annotations

from src.application.services.engine_bootstrap.signal_alpha_trigger_config_resolver import (
    resolve_alpha_trigger_config,
)
from src.application.services.engine_bootstrap.signal_archived_config_warnings import (
    _warn_archived_signal_config_changes,
)
from src.application.services.engine_bootstrap.signal_decision_policy_config_resolver import (
    resolve_decision_policy_config,
)
from src.application.services.signal_engine_config import (
    AnalystBearishFlagConfig,
    AnalystScoringConfig,
    BandarScoringConfig,
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    ForeignFlowScoreMappingConfig,
    ForwardPeScoringConfig,
    InsiderSellingFlagConfig,
    NeutralRegimeConfig,
    RegimeConditioningConfig,
    RiskOffRegimeConfig,
    SeasonalityScoringConfig,
    SignalClassificationConfig,
    SignalEngineConfig,
    SignalEnrichmentConfig,
    SignalFlagsConfig,
    SignalInputMappingConfig,
    SignalMissingDataConfig,
    SignalScoringConfig,
    ValuationStretchedFlagConfig,
    VolatileRegimeConfig,
)


def resolve_signal_engine_config(cfg: dict) -> SignalEngineConfig:
    root = cfg.get("signal_engine", {})
    classification = root.get("classification", {})
    missing = root.get("missing_data", {})
    scoring = root.get("scoring", {})
    enrichment = root.get("enrichment", {})
    input_mapping = root.get("input_mapping", {})
    foreign_flow_score_mapping = input_mapping.get("foreign_flow_score", {})
    bandar = scoring.get("bandar", {})
    seasonality = scoring.get("seasonality", {})
    analyst = scoring.get("analyst", {})
    forward_pe = scoring.get("forward_pe", {})
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
    _warn_archived_signal_config_changes(root)
    decision_policy = resolve_decision_policy_config(decision_cfg)
    alpha_trigger_cfg = resolve_alpha_trigger_config(root.get("alpha_trigger", {}))

    return SignalEngineConfig(
        classification=SignalClassificationConfig(
            strong_min_score=classification.get("strong_min_score", 70),
            moderate_min_score=classification.get("moderate_min_score", 45),
            enter_min_confidence=classification.get("enter_min_confidence", 0.70),
            watch_min_confidence=classification.get("watch_min_confidence", 0.40),
        ),
        missing_data=SignalMissingDataConfig(
            neutral_score=missing.get("neutral_score", 50.0),
            coverage_warning_missing_factors=missing.get("coverage_warning_missing_factors", 3),
        ),
        scoring=SignalScoringConfig(
            bandar=BandarScoringConfig(
                mandatory_signal_count=bandar.get("mandatory_signal_count", 3),
                signal_score_unit=bandar.get("signal_score_unit", 2),
                default_max_range=bandar.get("default_max_range", 6),
            ),
            seasonality=SeasonalityScoringConfig(
                tailwind_min_avg_return_pct=seasonality.get("tailwind_min_avg_return_pct", 0.0),
                tailwind_min_win_rate_pct=seasonality.get("tailwind_min_win_rate_pct", 50.0),
                headwind_max_avg_return_pct=seasonality.get("headwind_max_avg_return_pct", 0.0),
                headwind_max_win_rate_pct=seasonality.get("headwind_max_win_rate_pct", 50.0),
            ),
            analyst=AnalystScoringConfig(
                buy_score_max_points=analyst.get("buy_score_max_points", 60.0),
                upside_score_max_points=analyst.get("upside_score_max_points", 40.0),
                upside_cap_pct=analyst.get("upside_cap_pct", 30.0),
            ),
            forward_pe=ForwardPeScoringConfig(
                very_cheap_pe=forward_pe.get("very_cheap_pe", 10.0),
                cheap_pe=forward_pe.get("cheap_pe", 15.0),
                fair_pe=forward_pe.get("fair_pe", 20.0),
                expensive_pe=forward_pe.get("expensive_pe", 30.0),
                very_cheap_score=forward_pe.get("very_cheap_score", 95.0),
                cheap_score=forward_pe.get("cheap_score", 75.0),
                fair_score=forward_pe.get("fair_score", 50.0),
                expensive_score=forward_pe.get("expensive_score", 25.0),
                post_expensive_pe_step=forward_pe.get("post_expensive_pe_step", 10.0),
                post_expensive_score_decay=forward_pe.get("post_expensive_score_decay", 15.0),
            ),
        ),
        input_mapping=SignalInputMappingConfig(
            foreign_flow_score=ForeignFlowScoreMappingConfig(
                max_score=foreign_flow_score_mapping.get("max_score", 100.0),
                clamp=foreign_flow_score_mapping.get("clamp", True),
            ),
        ),
        enrichment=SignalEnrichmentConfig(
            insider_lookback_days=enrichment.get("insider_lookback_days", 90),
        ),
        evidence_groups=EvidenceGroupsConfig(
            setup_quality=EvidenceGroupConfig(
                weight=evidence_groups.get("setup_quality", {}).get("weight", 0.60),
            ),
            flow_confirmation=EvidenceGroupConfig(
                weight=evidence_groups.get("flow_confirmation", {}).get("weight", 0.40),
            ),
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
    )
