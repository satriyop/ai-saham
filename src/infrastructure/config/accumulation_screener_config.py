"""
Accumulation screener YAML config.

Layer: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.application.use_case.assess_accumulation_evidence_use_case import (
    AccumulationEvidencePolicy,
    BciEvidencePolicy,
    BollingerSqueezePolicy,
    EvidenceComponentPolicy,
    LinearSaturationPolicy,
    RsiEvidencePolicy,
    StreakEvidencePolicy,
)

ACCUMULATION_SCREENER_CONFIG_PATH = Path("config/accumulation_screener.yaml")


@dataclass(frozen=True)
class ScoreFilterConfig:
    enabled: bool = True
    value: float = 0.0


@dataclass(frozen=True)
class AccumulationDisplayConfig:
    enter_min_accum_score: float = 70.0
    watch_min_accum_score: float = 40.0
    coiled_spring_min_accum_score: float = 60.0
    coiled_spring_bb_pctile: float = 0.20


@dataclass(frozen=True)
class AccumulationScreenerConfig:
    evidence_policy: AccumulationEvidencePolicy = field(
        default_factory=AccumulationEvidencePolicy
    )
    min_accum_score: ScoreFilterConfig = field(
        default_factory=lambda: ScoreFilterConfig(enabled=True, value=70.0)
    )
    min_signal_score: ScoreFilterConfig = field(
        default_factory=lambda: ScoreFilterConfig(enabled=False, value=45.0)
    )
    display: AccumulationDisplayConfig = field(default_factory=AccumulationDisplayConfig)
    sort_primary: str = "trade_setup"
    sort_secondary: str = "signal_score"
    sort_tertiary: str = "accum_score"


def load_accumulation_screener_config(
    config_path: Path = ACCUMULATION_SCREENER_CONFIG_PATH,
) -> AccumulationScreenerConfig:
    defaults = AccumulationScreenerConfig()
    try:
        with open(config_path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return defaults

    try:
        root = raw.get("accumulation_screener") or raw
        evidence = root.get("evidence") or {}
        components = evidence.get("components") or {}
        filters = root.get("filters") or {}
        display = root.get("display") or {}
        sorting = root.get("sorting") or {}

        policy = _build_evidence_policy(evidence, components, defaults.evidence_policy)
        return AccumulationScreenerConfig(
            evidence_policy=policy,
            min_accum_score=_filter(
                filters.get("min_accum_score"),
                defaults.min_accum_score,
            ),
            min_signal_score=_filter(
                filters.get("min_signal_score"),
                defaults.min_signal_score,
            ),
            display=AccumulationDisplayConfig(
                enter_min_accum_score=_f(
                    display, "enter_min_accum_score", defaults.display.enter_min_accum_score
                ),
                watch_min_accum_score=_f(
                    display, "watch_min_accum_score", defaults.display.watch_min_accum_score
                ),
                coiled_spring_min_accum_score=_f(
                    display,
                    "coiled_spring_min_accum_score",
                    defaults.display.coiled_spring_min_accum_score,
                ),
                coiled_spring_bb_pctile=_f(
                    display, "coiled_spring_bb_pctile", defaults.display.coiled_spring_bb_pctile
                ),
            ),
            sort_primary=str(sorting.get("primary", defaults.sort_primary)),
            sort_secondary=str(sorting.get("secondary", defaults.sort_secondary)),
            sort_tertiary=str(sorting.get("tertiary", defaults.sort_tertiary)),
        )
    except Exception:
        return defaults


def _f(data: dict[str, Any], key: str, default: float) -> float:
    return float(data[key]) if key in data else default


def _b(data: dict[str, Any], key: str, default: bool) -> bool:
    return bool(data[key]) if key in data else default


def _filter(raw: Any, default: ScoreFilterConfig) -> ScoreFilterConfig:
    if not isinstance(raw, dict):
        return default
    return ScoreFilterConfig(
        enabled=_b(raw, "enabled", default.enabled),
        value=_f(raw, "value", default.value),
    )


def _component(
    raw: Any,
    default: EvidenceComponentPolicy,
) -> EvidenceComponentPolicy:
    if not isinstance(raw, dict):
        return default
    return EvidenceComponentPolicy(
        enabled=_b(raw, "enabled", default.enabled),
        weight=_f(raw, "weight", default.weight),
    )


def _build_evidence_policy(
    evidence: dict[str, Any],
    components: dict[str, Any],
    default: AccumulationEvidencePolicy,
) -> AccumulationEvidencePolicy:
    consistency = _component(components.get("consistency"), default.consistency)

    streak_raw = components.get("streak") or {}
    streak = StreakEvidencePolicy(
        enabled=_b(streak_raw, "enabled", default.streak.enabled),
        weight=_f(streak_raw, "weight", default.streak.weight),
        tau_days=_f(streak_raw, "tau_days", default.streak.tau_days),
    )

    vwap_raw = components.get("vwap_discount") or {}
    vwap = LinearSaturationPolicy(
        enabled=_b(vwap_raw, "enabled", default.vwap_discount.enabled),
        weight=_f(vwap_raw, "weight", default.vwap_discount.weight),
        saturate_at=_f(vwap_raw, "saturate_pct", default.vwap_discount.saturate_at),
    )

    rsi_raw = components.get("rsi_headroom") or {}
    rsi = RsiEvidencePolicy(
        enabled=_b(rsi_raw, "enabled", default.rsi_headroom.enabled),
        weight=_f(rsi_raw, "weight", default.rsi_headroom.weight),
        low=_f(rsi_raw, "low", default.rsi_headroom.low),
        peak=_f(rsi_raw, "peak", default.rsi_headroom.peak),
        high=_f(rsi_raw, "high", default.rsi_headroom.high),
        missing_fraction=_f(
            rsi_raw, "missing_fraction", default.rsi_headroom.missing_fraction
        ),
    )

    flow_raw = components.get("foreign_flow_ratio") or {}
    flow = LinearSaturationPolicy(
        enabled=_b(flow_raw, "enabled", default.foreign_flow_ratio.enabled),
        weight=_f(flow_raw, "weight", default.foreign_flow_ratio.weight),
        saturate_at=_f(flow_raw, "saturate_pct", default.foreign_flow_ratio.saturate_at),
    )

    bb_raw = components.get("bb_squeeze") or {}
    bb = BollingerSqueezePolicy(
        enabled=_b(bb_raw, "enabled", default.bb_squeeze.enabled),
        weight=_f(bb_raw, "weight", default.bb_squeeze.weight),
        tight_pctile=_f(bb_raw, "tight_pctile", default.bb_squeeze.tight_pctile),
        loose_pctile=_f(bb_raw, "loose_pctile", default.bb_squeeze.loose_pctile),
    )

    bci_raw = components.get("bci") or {}
    bci = BciEvidencePolicy(
        enabled=_b(bci_raw, "enabled", default.bci.enabled),
        cluster_points=_f(bci_raw, "cluster_points", default.bci.cluster_points),
        stable_points=_f(bci_raw, "stable_points", default.bci.stable_points),
    )

    return AccumulationEvidencePolicy(
        max_score=_f(evidence, "max_score", default.max_score),
        consistency=consistency,
        streak=streak,
        vwap_discount=vwap,
        rsi_headroom=rsi,
        foreign_flow_ratio=flow,
        bb_squeeze=bb,
        bci=bci,
    )
