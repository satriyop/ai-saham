"""
Signal engine config resolving.

Pure config normalization for the Signal Engine: reads signal_engine.yaml,
applies defaults, builds SignalEngineConfig/DecisionPolicy value objects, and
emits the existing archived-config warnings. No engine construction, no
infrastructure wiring.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.application.services.engine_bootstrap.config_resolvers import (
    _load_engine_config,
)
from src.application.services.engine_bootstrap.evidence_authority_validation import (
    _resolve_evidence_promotion_record,
    _validate_evidence_authority_promotion,
)

logger = logging.getLogger(__name__)


def _resolve_signal_weights(cfg: dict) -> dict[str, float] | None:
    """
    Parse enabled signal factors and return renormalized weights.

    Returns None when config is absent/empty so AssessSignalUseCase falls back
    to its built-in _DEFAULT_WEIGHTS (identical to historical behavior).
    """
    factors = cfg.get("signal_engine", {}).get("factors", {})
    active = {
        name: data["weight"]
        for name, data in factors.items()
        if data.get("enabled", True)
    }
    if not active:
        return None
    total = sum(active.values())
    return {name: w / total for name, w in active.items()}


def _resolve_signal_raw_weights(cfg: dict) -> dict[str, float] | None:
    """
    Return raw configured factor weights (before renormalization) for enabled factors.

    Mirrors _resolve_signal_weights but skips the renormalization step so callers
    (e.g. the signal-audit observability command) can display the weights exactly
    as authored in signal_engine.yaml. Returns None when config is absent/empty.
    """
    factors = cfg.get("signal_engine", {}).get("factors", {})
    active = {
        name: data["weight"]
        for name, data in factors.items()
        if data.get("enabled", True)
    }
    return active or None


def load_signal_weight_tables():
    """
    Load (active_weights, raw_weights, config) for signal-audit observability.

    active_weights: renormalized weights actually used by the current engine.
    raw_weights:    raw configured weights from YAML (pre-renormalization).
    config:         resolved SignalEngineConfig.

    Falls back to AssessSignalUseCase._DEFAULT_WEIGHTS when config is absent so the
    audit reflects the same weights the production engine would use.
    """
    from src.application.use_case.assess_signal_use_case import _DEFAULT_WEIGHTS
    from src.infrastructure.config.app_config import APP_CFG

    cfg = _load_engine_config(Path(APP_CFG.config_paths.signal_engine))
    active = _resolve_signal_weights(cfg) or dict(_DEFAULT_WEIGHTS)
    raw = _resolve_signal_raw_weights(cfg) or dict(_DEFAULT_WEIGHTS)
    signal_config = _resolve_signal_config(cfg)
    return active, raw, signal_config


def _resolve_signal_config(cfg: dict):
    from src.application.use_case.assess_signal_use_case import (
        AlphaTriggerConfig,
        AnalystBearishFlagConfig,
        AnalystScoringConfig,
        BandarScoringConfig,
        DecisionPolicyConfig,
        EvidenceGroupConfig,
        EvidenceGroupsConfig,
        ForeignFlowScoreMappingConfig,
        ForwardPeScoringConfig,
        InsiderSellingFlagConfig,
        NeutralRegimeConfig,
        RegimeConditioningConfig,
        RegimeDecisionPolicyConfig,
        RiskOffRegimeConfig,
        SeasonalityScoringConfig,
        SetupRegimeActionConfig,
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
    from src.domain.value_objects.alpha_trigger_score import (
        EvidenceAuthorityStatus,
        EvidencePromotionRecord,
        EvidenceRegistration,
    )

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
    decision_policy = _resolve_decision_policy_config(
        decision_cfg,
        DecisionPolicyConfig,
        RegimeDecisionPolicyConfig,
        SetupRegimeActionConfig,
    )
    alpha_trigger_cfg = _resolve_alpha_trigger_config(
        root.get("alpha_trigger", {}),
        AlphaTriggerConfig,
        EvidenceRegistration,
        EvidencePromotionRecord,
        EvidenceAuthorityStatus,
    )

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


def _resolve_alpha_trigger_config(
    raw: dict,
    alpha_trigger_cls,
    evidence_registration_cls,
    evidence_promotion_record_cls,
    evidence_status_cls,
):
    defaults = alpha_trigger_cls()
    if not raw:
        return defaults

    route_fractions = {
        horizon: dict(groups)
        for horizon, groups in defaults.route_fractions.items()
    }
    for horizon, groups in (raw.get("route_fractions") or {}).items():
        resolved_groups = dict(route_fractions.get(horizon, {}))
        for group, group_cfg in (groups or {}).items():
            alpha_fraction = (
                (group_cfg or {}).get("alpha_fraction")
                if isinstance(group_cfg, dict) else group_cfg
            )
            value = float(alpha_fraction)
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"signal_engine.alpha_trigger.route_fractions."
                    f"{horizon}.{group}.alpha_fraction must be 0.0-1.0"
                )
            resolved_groups[group] = value
        route_fractions[horizon] = resolved_groups

    group_weights = dict(defaults.group_weights)
    for group, value in (raw.get("group_weights") or {}).items():
        weight = float(value)
        if weight < 0.0:
            raise ValueError(
                f"signal_engine.alpha_trigger.group_weights.{group} must be >= 0.0"
            )
        group_weights[group] = weight
    if sum(group_weights.values()) <= 0:
        raise ValueError("signal_engine.alpha_trigger.group_weights must sum above 0")

    horizon_alpha_weights = dict(defaults.horizon_alpha_weights)
    for horizon, value in (raw.get("horizon_alpha_weights") or {}).items():
        weight = float(value)
        if not (0.0 <= weight <= 1.0):
            raise ValueError(
                f"signal_engine.alpha_trigger.horizon_alpha_weights.{horizon} "
                "must be 0.0-1.0"
            )
        horizon_alpha_weights[horizon] = weight

    low_weight_cap = float(raw.get("low_weight_cap", defaults.low_weight_cap))
    if not (0.0 <= low_weight_cap <= 1.0):
        raise ValueError("signal_engine.alpha_trigger.low_weight_cap must be 0.0-1.0")

    registrations = dict(defaults.evidence_registrations)
    for name, reg in (raw.get("evidence_registrations") or {}).items():
        status_raw = str((reg or {}).get("status", "DIAGNOSTIC")).upper()
        try:
            status = evidence_status_cls(status_raw)
        except ValueError:
            raise ValueError(
                f"signal_engine.alpha_trigger.evidence_registrations.{name}.status "
                "must be DIAGNOSTIC, LOW_WEIGHT, or PRODUCTION"
            )
        promotion = _resolve_evidence_promotion_record(
            name=name,
            status=status,
            raw=(reg or {}).get("promotion"),
            evidence_promotion_record_cls=evidence_promotion_record_cls,
            evidence_status_cls=evidence_status_cls,
        )
        _validate_evidence_authority_promotion(
            name=name,
            status=status,
            promotion=promotion,
        )
        registrations[name] = evidence_registration_cls(
            evidence_name=name,
            status=status,
            low_weight_cap=float((reg or {}).get("low_weight_cap", low_weight_cap)),
            promotion_requires=tuple(
                str(v) for v in (reg or {}).get("promotion_requires", ())
            ),
            promoted_by=(reg or {}).get("promoted_by"),
            promoted_date=(reg or {}).get("promoted_date"),
            promotion=promotion,
        )

    return alpha_trigger_cls(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        default_horizon=str(raw.get("default_horizon", defaults.default_horizon)),
        group_weights=group_weights,
        route_fractions=route_fractions,
        horizon_alpha_weights=horizon_alpha_weights,
        low_weight_cap=low_weight_cap,
        evidence_registrations=registrations,
    )


_ARCHIVED_SIGNAL_CONFIG_DEFAULTS: dict[str, object] = {
    "signal_engine.factors.bandar_intensity.enabled": True,
    "signal_engine.factors.bandar_intensity.weight": 0.20,
    "signal_engine.factors.foreign_flow_quality.enabled": True,
    "signal_engine.factors.foreign_flow_quality.weight": 0.20,
    "signal_engine.factors.insider_activity.enabled": True,
    "signal_engine.factors.insider_activity.weight": 0.20,
    "signal_engine.factors.seasonality_edge.enabled": True,
    "signal_engine.factors.seasonality_edge.weight": 0.15,
    "signal_engine.factors.analyst_consensus.enabled": True,
    "signal_engine.factors.analyst_consensus.weight": 0.15,
    "signal_engine.factors.forward_valuation.enabled": True,
    "signal_engine.factors.forward_valuation.weight": 0.10,
    "signal_engine.scoring.seasonality.tailwind_min_avg_return_pct": 0.0,
    "signal_engine.scoring.seasonality.tailwind_min_win_rate_pct": 50.0,
    "signal_engine.scoring.seasonality.headwind_max_avg_return_pct": 0.0,
    "signal_engine.scoring.seasonality.headwind_max_win_rate_pct": 50.0,
    "signal_engine.scoring.analyst.buy_score_max_points": 60.0,
    "signal_engine.scoring.analyst.upside_score_max_points": 40.0,
    "signal_engine.scoring.analyst.upside_cap_pct": 30.0,
    "signal_engine.scoring.forward_pe.very_cheap_pe": 10.0,
    "signal_engine.scoring.forward_pe.cheap_pe": 15.0,
    "signal_engine.scoring.forward_pe.fair_pe": 20.0,
    "signal_engine.scoring.forward_pe.expensive_pe": 30.0,
    "signal_engine.scoring.forward_pe.very_cheap_score": 95.0,
    "signal_engine.scoring.forward_pe.cheap_score": 75.0,
    "signal_engine.scoring.forward_pe.fair_score": 50.0,
    "signal_engine.scoring.forward_pe.expensive_score": 25.0,
    "signal_engine.scoring.forward_pe.post_expensive_pe_step": 10.0,
    "signal_engine.scoring.forward_pe.post_expensive_score_decay": 15.0,
}

_ARCHIVED_FACTOR_CONFIG_WARNING = (
    "%s is archived/baseline-only and does not tune canonical staged evidence "
    "scoring. Tune evidence_groups.*, flags.*, alpha_trigger.*, or "
    "decision_policy.* instead."
)

_DIAGNOSTIC_SCORER_CONFIG_WARNING = (
    "%s is a shared baseline / diagnostic company-quality scorer and is not "
    "Phase I patch-eligible. It does not affect canonical production score while "
    "company_quality_context remains DIAGNOSTIC."
)


def _warn_archived_signal_config_changes(root: dict) -> None:
    """Warn when archived six-factor config is authored away from defaults."""
    for path, default in _ARCHIVED_SIGNAL_CONFIG_DEFAULTS.items():
        leaf_path = path.removeprefix("signal_engine.").split(".")
        found, value = _nested_lookup(root, leaf_path)
        if found and value != default:
            if path.startswith("signal_engine.factors."):
                logger.warning(_ARCHIVED_FACTOR_CONFIG_WARNING, path)
            else:
                logger.warning(_DIAGNOSTIC_SCORER_CONFIG_WARNING, path)


def _nested_lookup(data: dict, path: list[str]) -> tuple[bool, object | None]:
    current: object = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _resolve_decision_policy_config(
    decision_cfg: dict,
    decision_policy_cls,
    regime_policy_cls,
    setup_action_cls,
):
    allowed_regimes = {"RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE"}
    allowed_decisions = {"ENTER", "WATCH", "AVOID"}

    default_policy = decision_policy_cls()
    if not decision_cfg:
        return default_policy

    regime_cfg = decision_cfg.get("regime_policy")
    if not isinstance(regime_cfg, dict):
        raise ValueError("signal_engine.decision_policy.regime_policy is required")

    missing = allowed_regimes - set(regime_cfg)
    extra = set(regime_cfg) - allowed_regimes
    if missing:
        raise ValueError(
            "signal_engine.decision_policy.regime_policy missing regimes: "
            + ", ".join(sorted(missing))
        )
    if extra:
        raise ValueError(
            "signal_engine.decision_policy.regime_policy has unknown regimes: "
            + ", ".join(sorted(extra))
        )

    resolved_regimes = {}
    for regime in sorted(allowed_regimes):
        raw = regime_cfg[regime] or {}
        decision = raw.get("max_decision")
        if decision not in allowed_decisions:
            raise ValueError(
                f"Invalid max_decision for {regime}: {decision!r}"
            )
        resolved_regimes[regime] = regime_policy_cls(
            enter_allowed=bool(raw.get("enter_allowed", True)),
            max_decision=decision,
            regime_size_multiplier=float(raw.get("regime_size_multiplier", 1.0)),
            enter_threshold=raw.get("enter_threshold"),
            watch_threshold=int(raw.get("watch_threshold", 45)),
            min_coverage=float(raw.get("min_coverage", 0.0)),
            min_conviction=float(raw.get("min_conviction", 0.0)),
        )

    raw_actions = decision_cfg.get("setup_regime_actions", {})
    resolved_actions = dict(default_policy.setup_regime_actions)
    for name, raw in raw_actions.items():
        decision = (raw or {}).get("max_decision")
        if decision not in allowed_decisions:
            raise ValueError(
                f"Invalid setup_regime_actions.{name}.max_decision: {decision!r}"
            )
        resolved_actions[name] = setup_action_cls(max_decision=decision)

    raw_setup_policy = decision_cfg.get("setup_regime_policy", {})
    resolved_setup_policy: dict[str, dict[str, str]] = {}
    for family, by_regime in raw_setup_policy.items():
        if not isinstance(by_regime, dict):
            raise ValueError(f"setup_regime_policy.{family} must map regimes to actions")
        resolved_family: dict[str, str] = {}
        for regime, action_name in by_regime.items():
            if regime not in allowed_regimes:
                raise ValueError(
                    f"Invalid setup_regime_policy.{family} regime: {regime!r}"
                )
            if action_name not in resolved_actions:
                raise ValueError(
                    f"Invalid setup_regime_policy.{family}.{regime} action: "
                    f"{action_name!r}"
                )
            resolved_family[regime] = action_name
        resolved_setup_policy[family] = resolved_family

    return decision_policy_cls(
        regime_policy=resolved_regimes,
        setup_regime_policy=resolved_setup_policy,
        setup_regime_actions=resolved_actions,
    )


