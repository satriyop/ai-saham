"""
Application bootstrap utilities.

Provides functions for initializing application services with plugins
and persisted formulas.
"""

from __future__ import annotations

from datetime import date
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from src.application.formula.parser import parse
from src.application.services.indicator_registry import IndicatorRegistry

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.infrastructure.persistence.formula_storage import FormulaStorage
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

logger = logging.getLogger(__name__)


# ── Engine config helpers ─────────────────────────────────────────────────────

def _load_engine_config(path: Path) -> dict:
    """Load a YAML engine config file. Returns empty dict if file is absent."""
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


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
        EvidenceGroupConfig,
        EvidenceGroupsConfig,
        ForeignFlowScoreMappingConfig,
        AnalystScoringConfig,
        BandarScoringConfig,
        DecisionPolicyConfig,
        ForwardPeScoringConfig,
        InsiderSellingFlagConfig,
        NeutralRegimeConfig,
        RegimeConditioningConfig,
        RegimeDecisionPolicyConfig,
        RiskOffRegimeConfig,
        SeasonalityScoringConfig,
        SignalClassificationConfig,
        SignalEnrichmentConfig,
        SignalEngineConfig,
        SignalFlagsConfig,
        SignalInputMappingConfig,
        SignalMissingDataConfig,
        SignalScoringConfig,
        SetupRegimeActionConfig,
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
                max_score=foreign_flow_score_mapping.get("max_score", 120.0),
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


_BASELINE_EVIDENCE_AUTHORITY = {
    ("setup_quality", "PRODUCTION"),
    ("institutional_flow", "PRODUCTION"),
}

_PROMOTED_STATUSES = {"LOW_WEIGHT", "PRODUCTION"}

_PHASE_I_PROMOTION_GATES = {
    "min_is_labels": (60.0, "min"),
    "min_oos_labels": (30.0, "min"),
    "min_oos_profit_factor": (1.15, "min"),
    "min_oos_avg_return_pct": (0.0, "min"),
    "max_drawdown_regression_pct": (0.0, "max"),
}


def _resolve_evidence_promotion_record(
    *,
    name: str,
    status,
    raw,
    evidence_promotion_record_cls,
    evidence_status_cls,
):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion must be a mapping"
        )

    promoted_to_raw = str(raw.get("promoted_to", "")).upper()
    try:
        promoted_to = evidence_status_cls(promoted_to_raw)
    except ValueError:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.promoted_to must be DIAGNOSTIC, LOW_WEIGHT, or PRODUCTION"
        )

    record = evidence_promotion_record_cls(
        target=_promotion_required_str(name, raw, "target"),
        evidence_name=_promotion_required_str(name, raw, "evidence_name"),
        promoted_to=promoted_to,
        promoted_by=_promotion_required_str(name, raw, "promoted_by"),
        promoted_date=_promotion_required_str(name, raw, "promoted_date"),
        attribution_ref=_promotion_required_str(name, raw, "attribution_ref"),
        requirements=_promotion_requirements(name, raw.get("requirements")),
    )
    _validate_promotion_record(name=name, status=status, promotion=record)
    return record


def _promotion_required_str(name: str, raw: dict, field: str) -> str:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.{field} is required"
        )
    return str(value).strip()


def _promotion_requirements(name: str, raw_requirements) -> tuple[tuple[str, float], ...]:
    if not isinstance(raw_requirements, dict):
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.requirements must be a mapping"
        )
    requirements: list[tuple[str, float]] = []
    for key in _PHASE_I_PROMOTION_GATES:
        if key not in raw_requirements:
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} is required"
            )
        try:
            requirements.append((key, float(raw_requirements[key])))
        except (TypeError, ValueError):
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} must be numeric"
            )
    return tuple(requirements)


def _validate_evidence_authority_promotion(*, name: str, status, promotion) -> None:
    status_value = status.value if hasattr(status, "value") else str(status)
    if (name, status_value) in _BASELINE_EVIDENCE_AUTHORITY:
        return
    if status_value in _PROMOTED_STATUSES and promotion is None:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion is required when status is {status_value}"
        )


def _validate_promotion_record(*, name: str, status, promotion) -> None:
    status_value = status.value if hasattr(status, "value") else str(status)
    if promotion.evidence_name != name:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.evidence_name must match registration key"
        )
    promoted_to = (
        promotion.promoted_to.value
        if hasattr(promotion.promoted_to, "value") else str(promotion.promoted_to)
    )
    if promoted_to != status_value:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.promoted_to must equal status"
        )
    try:
        date.fromisoformat(promotion.promoted_date)
    except ValueError:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.promoted_date must be a valid ISO date"
        )
    requirements = promotion.requirements_dict
    for key, (canonical, direction) in _PHASE_I_PROMOTION_GATES.items():
        value = requirements[key]
        if direction == "min" and value < canonical:
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} must be >= {canonical:g}"
            )
        if direction == "max" and value > canonical:
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} must be <= {canonical:g}"
            )


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


def _resolve_risk_gates(cfg: dict) -> tuple[list, list]:
    """
    Parse enabled risk gates and return (structural_gates, execution_gates).

    When config is absent/empty, defaults match the previous hardcoded values.
    """
    from src.domain.rules.bandar_gate import BandarGate, BandarGateConfig
    from src.domain.rules.free_float_gate import FreeFloatGate, FreeFloatGatePolicy
    from src.domain.rules.fundamental_gate import FundamentalGate, FundamentalGatePolicy
    from src.domain.rules.liquidity_gate import LiquidityGate, LiquidityGatePolicy

    gates = cfg.get("risk_engine", {}).get("gates", {})

    structural = []
    fund = gates.get("fundamental", {})
    if fund.get("enabled", True):
        structural.append(FundamentalGate(
            distress_threshold=fund.get("piotroski_min", 3),
            policy=FundamentalGatePolicy(
                missing_data_action=fund.get("missing_data_action", "skip"),
                missing_data_confidence=fund.get("missing_data_confidence", 0),
                triggered_confidence=fund.get("triggered_confidence", 100),
                pass_confidence=fund.get("pass_confidence", 100),
            ),
        ))

    liq = gates.get("liquidity", {})
    if liq.get("enabled", True):
        structural.append(LiquidityGate(
            third_liner_cap_idr=liq.get("market_cap_floor_idr", 1_000_000_000_000),
            liquidity_floor_idr=liq.get("median_tx_floor_idr", 5_000_000_000),
            lookback_days=liq.get("lookback_days", 20),
            policy=LiquidityGatePolicy(
                missing_data_action=liq.get("missing_data_action", "skip"),
                missing_data_confidence=liq.get("missing_data_confidence", 0),
                triggered_confidence=liq.get("triggered_confidence", 100),
                pass_confidence=liq.get("pass_confidence", 100),
            ),
        ))

    ff = gates.get("free_float", {})
    if ff.get("enabled", True):
        structural.append(FreeFloatGate(
            min_free_float_pct=ff.get("min_free_float_pct", 15.0),
            policy=FreeFloatGatePolicy(
                missing_data_action=ff.get("missing_data_action", "skip"),
                missing_data_confidence=ff.get("missing_data_confidence", 0),
                triggered_confidence=ff.get("triggered_confidence", 100),
                pass_confidence=ff.get("pass_confidence", 100),
            ),
        ))

    execution = []
    bandar = gates.get("bandar", {})
    if bandar.get("enabled", True):
        execution.append(BandarGate(
            BandarGateConfig(
                distribution_labels=frozenset(bandar.get("distribution_labels", [
                    "Small Dist", "Big Dist",
                ])),
                missing_data_action=bandar.get("missing_data_action", "skip"),
                missing_data_confidence=bandar.get("missing_data_confidence", 0),
                triggered_confidence=bandar.get("triggered_confidence", 80),
                pass_confidence=bandar.get("pass_confidence", 100),
            )
        ))

    return structural, execution


def _resolve_risk_indicator_defaults(cfg: dict):
    from src.application.services.risk_engine import RiskIndicatorDefaults

    indicators = cfg.get("risk_engine", {}).get("indicators", {})
    return RiskIndicatorDefaults(
        sma_period=indicators.get("sma_period", 20),
        ema_period=indicators.get("ema_period", 20),
        rsi_period=indicators.get("rsi_period", 14),
        history_days=indicators.get("history_days", 365),
        gate_recent_candle_lookback=indicators.get("gate_recent_candle_lookback", 20),
    )


def _resolve_market_context_gate(cfg: dict):
    from src.application.services.risk_engine import MarketContextGateConfig

    gate = cfg.get("risk_engine", {}).get("market_context_gate", {})
    return MarketContextGateConfig(
        enabled=gate.get("enabled", True),
        block_when_gate_tightening=gate.get("block_when_gate_tightening", True),
        gate_is_structural=gate.get("gate_is_structural", True),
        label_prefix=gate.get("label_prefix", "regime"),
    )


def _resolve_indicator_evaluator_config(cfg: dict):
    from src.application.services.indicator_evaluator import IndicatorEvaluatorConfig

    technical = cfg.get("risk_engine", {}).get("gates", {}).get("technical", {})
    evaluator = technical.get("evaluator", {})
    return IndicatorEvaluatorConfig(
        rsi_overbought=evaluator.get("rsi_overbought", 70.0),
        rsi_oversold=evaluator.get("rsi_oversold", 30.0),
        agreement_count=evaluator.get("agreement_count", 2),
        full_agreement_confidence=evaluator.get("full_agreement_confidence", 100),
        partial_agreement_confidence=evaluator.get("partial_agreement_confidence", 50),
    )


def _resolve_technical_gate_config(cfg: dict):
    from src.domain.rules.technical_gate import TechnicalGateConfig

    technical = cfg.get("risk_engine", {}).get("gates", {}).get("technical", {})
    return TechnicalGateConfig(
        block_when_bearish=technical.get("block_when_bearish", True),
        missing_data_action=technical.get("missing_data_action", "skip"),
        missing_data_confidence=technical.get("missing_data_confidence", 0),
        pass_confidence=technical.get("pass_confidence", 100),
    )


# ── Factory functions ─────────────────────────────────────────────────────────

def create_indicator_registry(
    plugin_dir: str | None = None,
    formula_storage: "FormulaStorage | None" = None,
    load_formulas: bool = True,
    broker_repository: "BrokerDataRepository | None" = None,
    market_repository: "MarketDataRepository | None" = None,
    index_ticker: str = "IHSG",
) -> IndicatorRegistry:
    """
    Create an IndicatorRegistry with plugins and formulas loaded.

    Discovers plugins from the specified directory (or default plugins/indicators/)
    and registers them. Optionally loads persisted formulas from storage.
    Gracefully handles missing directories, invalid plugins, and invalid formulas.

    Args:
        plugin_dir: Optional path to plugin directory. None uses default.
        formula_storage: Optional FormulaStorage instance for loading formulas.
                        If None and load_formulas is True, creates default storage.
        load_formulas: Whether to load formulas from storage. Default True.

    Returns:
        IndicatorRegistry with built-in indicators, discovered plugins,
        and loaded formulas.
    """
    registry = IndicatorRegistry(
        broker_repository=broker_repository,
        market_repository=market_repository,
        index_ticker=index_ticker,
    )

    # Load plugins
    from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader

    loader = IndicatorPluginLoader(Path(plugin_dir) if plugin_dir else None)
    plugins = loader.discover()

    # Register each plugin
    for plugin_class in plugins:
        try:
            registry.register_plugin(plugin_class)
            logger.debug(f"Registered plugin: {plugin_class.name}")
        except Exception as e:
            logger.warning(f"Failed to register plugin {plugin_class.name}: {e}")

    # Load persisted formulas
    if load_formulas:
        _load_formulas_into_registry(registry, formula_storage)

    return registry


def create_risk_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
) -> "RiskEngine":
    """
    Create a fully-configured RiskEngine with all three gates wired.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject FundamentalsProvider and
            BandarDetectorProvider so FundamentalGate and BandarGate
            can fire from the engine's own assess() call.
            When False (default), LiquidityGate still fires from candle
            data; the other gates skip gracefully.
    """
    from pathlib import Path as _Path

    from src.application.services.risk_engine import RiskEngine
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    resolved = _Path(db_path)
    repository = SQLiteMarketRepository(db_path=resolved)
    broker_repository = SQLiteBrokerRepository(db_path=resolved)
    registry = create_indicator_registry(
        market_repository=repository,
        broker_repository=broker_repository,
    )

    from src.infrastructure.config.app_config import APP_CFG

    cfg = _load_engine_config(Path(APP_CFG.config_paths.risk_engine))
    structural_gates, execution_gates = _resolve_risk_gates(cfg)
    indicator_defaults = _resolve_risk_indicator_defaults(cfg)
    market_context_gate = _resolve_market_context_gate(cfg)
    indicator_evaluator_config = _resolve_indicator_evaluator_config(cfg)
    technical_gate_config = _resolve_technical_gate_config(cfg)

    fund_prov = None
    bandar_prov = None
    shareholding_prov = None
    if with_enrichment:
        from src.infrastructure.browser.stockbit_fundamentals import (
            StockbitFundamentalsProvider,
        )
        from src.infrastructure.browser.stockbit_bandar import (
            StockbitBandarDetectorProvider,
        )
        from src.infrastructure.browser.stockbit_shareholding import (
            StockbitShareholdingProvider,
        )

        fund_prov = StockbitFundamentalsProvider(api_client=None, db_path=resolved)
        bandar_prov = StockbitBandarDetectorProvider(api_client=None, db_path=resolved)
        shareholding_prov = StockbitShareholdingProvider(api_client=None, db_path=resolved)

    from src.application.services.indicator_evaluator import IndicatorEvaluator

    return RiskEngine(
        repository=repository,
        registry=registry,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
        fundamentals_provider=fund_prov,
        bandar_provider=bandar_prov,
        shareholding_provider=shareholding_prov,
        indicator_evaluator=IndicatorEvaluator(indicator_evaluator_config),
        indicator_defaults=indicator_defaults,
        market_context_gate=market_context_gate,
        technical_gate_config=technical_gate_config,
    )


def create_signal_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
) -> "SignalEngine":
    """
    Create a fully-configured SignalEngine.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject all 5 Stockbit enrichment providers
            (bandar, fundamentals, seasonality, analyst, forward_estimates) using
            the SQLite cache so evaluate() works without a live broker session.
            When False (default), all providers are None and all factors fall
            back to neutral (50.0) — useful for testing the engine wiring.
    """
    from pathlib import Path as _Path

    from src.application.services.signal_engine import SignalEngine

    from src.infrastructure.config.app_config import APP_CFG

    cfg = _load_engine_config(Path(APP_CFG.config_paths.signal_engine))
    weights = _resolve_signal_weights(cfg)
    signal_config = _resolve_signal_config(cfg)

    if not with_enrichment:
        return SignalEngine(weights=weights, config=signal_config)

    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

    resolved = _Path(db_path)
    market_repository = SQLiteMarketRepository(db_path=resolved)

    def _latest_close(ticker: str) -> float | None:
        candles = market_repository.get_candles(ticker)
        if not candles:
            return None
        return float(candles[-1].close)

    return SignalEngine(
        bandar_provider=StockbitBandarDetectorProvider(api_client=None, db_path=resolved),
        insider_activity_provider=StockbitInsiderActivityProvider(api_client=None, db_path=resolved),
        seasonality_provider=StockbitSeasonalityProvider(api_client=None, db_path=resolved),
        analyst_provider=StockbitAnalystConsensusProvider(api_client=None, db_path=resolved),
        forward_estimates_provider=StockbitForwardEstimatesProvider(
            api_client=None, db_path=resolved
        ),
        latest_price_provider=_latest_close,
        weights=weights,
        config=signal_config,
    )


def _load_formulas_into_registry(
    registry: IndicatorRegistry,
    formula_storage: "FormulaStorage | None" = None,
) -> None:
    """
    Load persisted formulas into the registry.

    Args:
        registry: IndicatorRegistry to load formulas into.
        formula_storage: Optional FormulaStorage instance. If None,
                        creates default storage from config/formulas.yaml.
    """
    # Create default storage if not provided
    if formula_storage is None:
        from src.infrastructure.persistence.formula_storage import FormulaStorage

        formula_storage = FormulaStorage()

    # Load all formulas
    try:
        stored_formulas = formula_storage.load_all()
    except Exception as e:
        logger.warning(f"Failed to load formulas from storage: {e}")
        return

    if not stored_formulas:
        logger.debug("No formulas found in storage")
        return

    # Register each formula
    loaded_count = 0
    for name, stored in stored_formulas.items():
        try:
            # Parse formula string to AST
            ast = parse(stored.formula)

            # Register in registry
            registry.register_formula(name, ast)
            logger.debug(f"Loaded formula from storage: {name}")
            loaded_count += 1

        except Exception as e:
            logger.warning(f"Failed to load formula {name}: {e}")

    if loaded_count > 0:
        logger.info(f"Loaded {loaded_count} formulas from storage")
