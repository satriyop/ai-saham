"""
Signal engine alpha/trigger config resolving.

Pure config normalization for the alpha_trigger section of
signal_engine.yaml: route fractions, group weights, horizon alpha weights,
low weight cap, and evidence registration/promotion records. No engine
construction, no infrastructure wiring.

The `market_context` Alpha/Trigger group identity was removed
(SECTOR-CONTEXT-IDENTITY); the SectorContextEvidence producer registers under
`sector_context`, not the genuine market-wide MarketContext. New config
supplying the removed key under group_weights, any route_fractions horizon, or
evidence_registrations is rejected explicitly rather than silently merged or
translated — the resolver never aliases, normalizes, or produces both group
identities at once.
"""

from __future__ import annotations

from src.application.services.engine_bootstrap.evidence_authority_validation import (
    _resolve_evidence_promotion_record,
    _validate_evidence_authority_promotion,
)
from src.application.services.signal_engine_config import AlphaTriggerConfig
from src.domain.value_objects.alpha_trigger_score import (
    REMOVED_MARKET_CONTEXT_EVIDENCE_NAME,
    EvidenceAuthorityStatus,
    EvidencePromotionRecord,
    EvidenceRegistration,
)

_REMOVED_GROUP_MESSAGE = (
    "Alpha/Trigger group 'market_context' was removed; use 'sector_context' "
    "because its producer is SectorContextEvidence"
)


def resolve_alpha_trigger_config(raw: dict) -> AlphaTriggerConfig:
    defaults = AlphaTriggerConfig()
    if not raw:
        return defaults

    route_fractions = {
        horizon: dict(groups) for horizon, groups in defaults.route_fractions.items()
    }
    for horizon, groups in (raw.get("route_fractions") or {}).items():
        if REMOVED_MARKET_CONTEXT_EVIDENCE_NAME in (groups or {}):
            raise ValueError(
                f"signal_engine.alpha_trigger.route_fractions.{horizon}."
                f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME}: {_REMOVED_GROUP_MESSAGE}"
            )
        resolved_groups = dict(route_fractions.get(horizon, {}))
        for group, group_cfg in (groups or {}).items():
            alpha_fraction = (
                (group_cfg or {}).get("alpha_fraction")
                if isinstance(group_cfg, dict)
                else group_cfg
            )
            value = float(alpha_fraction)
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"signal_engine.alpha_trigger.route_fractions."
                    f"{horizon}.{group}.alpha_fraction must be 0.0-1.0"
                )
            resolved_groups[group] = value
        route_fractions[horizon] = resolved_groups

    raw_group_weights = raw.get("group_weights") or {}
    if REMOVED_MARKET_CONTEXT_EVIDENCE_NAME in raw_group_weights:
        raise ValueError(
            f"signal_engine.alpha_trigger.group_weights."
            f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME}: {_REMOVED_GROUP_MESSAGE}"
        )
    group_weights = dict(defaults.group_weights)
    for group, value in raw_group_weights.items():
        weight = float(value)
        if weight < 0.0:
            raise ValueError(f"signal_engine.alpha_trigger.group_weights.{group} must be >= 0.0")
        group_weights[group] = weight
    if sum(group_weights.values()) <= 0:
        raise ValueError("signal_engine.alpha_trigger.group_weights must sum above 0")

    horizon_alpha_weights = dict(defaults.horizon_alpha_weights)
    for horizon, value in (raw.get("horizon_alpha_weights") or {}).items():
        weight = float(value)
        if not (0.0 <= weight <= 1.0):
            raise ValueError(
                f"signal_engine.alpha_trigger.horizon_alpha_weights.{horizon} must be 0.0-1.0"
            )
        horizon_alpha_weights[horizon] = weight

    low_weight_cap = float(raw.get("low_weight_cap", defaults.low_weight_cap))
    if not (0.0 <= low_weight_cap <= 1.0):
        raise ValueError("signal_engine.alpha_trigger.low_weight_cap must be 0.0-1.0")

    raw_evidence_registrations = raw.get("evidence_registrations") or {}
    if REMOVED_MARKET_CONTEXT_EVIDENCE_NAME in raw_evidence_registrations:
        raise ValueError(
            f"signal_engine.alpha_trigger.evidence_registrations."
            f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME}: {_REMOVED_GROUP_MESSAGE}"
        )
    registrations = dict(defaults.evidence_registrations)
    for name, reg in raw_evidence_registrations.items():
        status_raw = str((reg or {}).get("status", "DIAGNOSTIC")).upper()
        try:
            status = EvidenceAuthorityStatus(status_raw)
        except ValueError:
            raise ValueError(
                f"signal_engine.alpha_trigger.evidence_registrations.{name}.status "
                "must be DIAGNOSTIC, LOW_WEIGHT, or PRODUCTION"
            )
        promotion = _resolve_evidence_promotion_record(
            name=name,
            status=status,
            raw=(reg or {}).get("promotion"),
            evidence_promotion_record_cls=EvidencePromotionRecord,
            evidence_status_cls=EvidenceAuthorityStatus,
        )
        _validate_evidence_authority_promotion(
            name=name,
            status=status,
            promotion=promotion,
        )
        registrations[name] = EvidenceRegistration(
            evidence_name=name,
            status=status,
            low_weight_cap=float((reg or {}).get("low_weight_cap", low_weight_cap)),
            promotion_requires=tuple(str(v) for v in (reg or {}).get("promotion_requires", ())),
            promoted_by=(reg or {}).get("promoted_by"),
            promoted_date=(reg or {}).get("promoted_date"),
            promotion=promotion,
        )

    return AlphaTriggerConfig(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        default_horizon=str(raw.get("default_horizon", defaults.default_horizon)),
        group_weights=group_weights,
        route_fractions=route_fractions,
        horizon_alpha_weights=horizon_alpha_weights,
        low_weight_cap=low_weight_cap,
        evidence_registrations=registrations,
    )
