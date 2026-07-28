"""
Parser for broker quality configuration fields.

Layer: Infrastructure
"""

from decimal import Decimal

from src.application.dto.swing_policy_config import SwingPolicyConfig
from src.infrastructure.config.swing_policy_config_primitives import (
    broker_codes_or_default,
    float_or_default,
    int_or_default,
)


def parse_broker_quality_fields(
    data: dict,
    defaults: SwingPolicyConfig,
) -> dict[str, object]:
    bq = data.get("broker_quality") or {}
    sm = bq.get("smart_money") or {}
    ns = bq.get("noise") or {}
    t1 = bq.get("tier1") or {}

    return {
        "smart_money_brokers": broker_codes_or_default(sm, defaults.smart_money_brokers),
        "noise_brokers": broker_codes_or_default(ns, defaults.noise_brokers),
        "smart_weight": Decimal(str(float_or_default(sm, "weight", float(defaults.smart_weight)))),
        "noise_weight": Decimal(str(float_or_default(ns, "weight", float(defaults.noise_weight)))),
        "smart_share_threshold_pct": float_or_default(
            bq, "smart_share_threshold_pct", defaults.smart_share_threshold_pct
        ),
        "smart_sell_min_share_pct": float_or_default(
            bq, "smart_sell_min_share_pct", defaults.smart_sell_min_share_pct
        ),
        "tier1_broker_codes": frozenset(
            broker_codes_or_default(t1, tuple(defaults.tier1_broker_codes))
        ),
        "bci_cluster_min_count": int_or_default(
            t1, "cluster_min_count", defaults.bci_cluster_min_count
        ),
        "bci_stable_min_count": int_or_default(
            t1, "stable_min_count", defaults.bci_stable_min_count
        ),
    }
