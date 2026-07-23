"""
Accumulation screener YAML config.

Layer: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.application.dto.accumulation_screen import AccumulationDerivedFeaturePolicy
from src.application.use_case.score_accum_use_case import (
    BciEvidencePolicy,
    BollingerSqueezePolicy,
    EvidenceComponentPolicy,
    AccumScorePolicy,
    LinearSaturationPolicy,
    RsiEvidencePolicy,
    StreakEvidencePolicy,
)
from src.infrastructure.config.app_config import AppConfig, load_app_config


def default_accumulation_screener_config_path(config: AppConfig | None = None) -> Path:
    cfg = config or load_app_config()
    return Path(cfg.config_paths.accumulation_screener)


@dataclass(frozen=True)
class ScoreFilterConfig:
    enabled: bool = True
    value: float = 0.0


@dataclass(frozen=True)
class AccumulationDisplayConfig:
    enter_min_accum_score: float = 58.3
    watch_min_accum_score: float = 33.3
    coiled_spring_min_accum_score: float = 50.0
    coiled_spring_bb_pctile: float = 0.20


@dataclass(frozen=True)
class AccumulationScreenerConfig:
    accum_score_policy: AccumScorePolicy = field(
        default_factory=AccumScorePolicy
    )
    derived_features: AccumulationDerivedFeaturePolicy = field(
        default_factory=AccumulationDerivedFeaturePolicy
    )
    min_accum_score: ScoreFilterConfig = field(
        default_factory=lambda: ScoreFilterConfig(enabled=True, value=58.3)
    )
    min_signal_score: ScoreFilterConfig = field(
        default_factory=lambda: ScoreFilterConfig(enabled=False, value=45.0)
    )
    display: AccumulationDisplayConfig = field(default_factory=AccumulationDisplayConfig)
    sort_primary: str = "trade_setup"
    sort_secondary: str = "signal_score"
    sort_tertiary: str = "accum_score"


def _reject_removed_accumulation_screener_keys(root: dict[str, Any]) -> None:
    removed = {
        "min_foreign_flow_score": "filters.min_accum_score",
        "foreign_flow_score_policy": "accum_score_policy (YAML evidence section)",
    }
    for key, replacement in removed.items():
        if key in root:
            raise ValueError(
                f"accumulation_screener.{key} was renamed (ADR-043); use {replacement} instead."
            )
    filters = root.get("filters") or {}
    if "min_foreign_flow_score" in filters:
        raise ValueError(
            "accumulation_screener.filters.min_foreign_flow_score was renamed to "
            "filters.min_accum_score (ADR-043)."
        )
    display = root.get("display") or {}
    for old_key in (
        "enter_min_foreign_flow_score",
        "watch_min_foreign_flow_score",
        "coiled_spring_min_foreign_flow_score",
    ):
        if old_key in display:
            raise ValueError(
                f"accumulation_screener.display.{old_key} was renamed (ADR-043); "
                "use the min_accum_score variant instead."
            )


def load_accumulation_screener_config(
    config_path: Path | None = None,
) -> AccumulationScreenerConfig:
    defaults = AccumulationScreenerConfig()
    path = config_path or default_accumulation_screener_config_path()
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return defaults

    try:
        root = raw.get("accumulation_screener") or raw
        _reject_removed_accumulation_screener_keys(root)
        evidence = root.get("evidence") or {}
        components = evidence.get("components") or {}
        derived_features = root.get("derived_features") or {}
        filters = root.get("filters") or {}
        display = root.get("display") or {}
        sorting = root.get("sorting") or {}

        policy = _build_accum_score_policy(
            evidence,
            components,
            defaults.accum_score_policy,
        )
        return AccumulationScreenerConfig(
            accum_score_policy=policy,
            derived_features=_build_derived_feature_policy(
                derived_features,
                defaults.derived_features,
            ),
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
    except ValueError:
        # Invalid material values and removed keys are contract errors, not a
        # reason to silently run the default deterministic model.
        raise
    except Exception:
        return defaults


def _f(data: dict[str, Any], key: str, default: float) -> float:
    return float(data[key]) if key in data else default


def _i(data: dict[str, Any], key: str, default: int) -> int:
    return int(data[key]) if key in data else default


def _positive_i(data: dict[str, Any], key: str, default: int) -> int:
    value = _i(data, key, default)
    if value < 1:
        raise ValueError(f"{key} must be >= 1")
    return value


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


def _build_accum_score_policy(
    evidence: dict[str, Any],
    components: dict[str, Any],
    default: AccumScorePolicy,
) -> AccumScorePolicy:
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
    if "missing_fraction" in rsi_raw:
        raise ValueError(
            "accumulation_screener.evidence.components.rsi_headroom."
            "missing_fraction was removed by DQ-001; missing RSI receives no points"
        )
    rsi = RsiEvidencePolicy(
        enabled=_b(rsi_raw, "enabled", default.rsi_headroom.enabled),
        weight=_f(rsi_raw, "weight", default.rsi_headroom.weight),
        low=_f(rsi_raw, "low", default.rsi_headroom.low),
        peak=_f(rsi_raw, "peak", default.rsi_headroom.peak),
        high=_f(rsi_raw, "high", default.rsi_headroom.high),
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

    return AccumScorePolicy(
        max_score=_f(evidence, "max_score", default.max_score),
        consistency=consistency,
        streak=streak,
        vwap_discount=vwap,
        rsi_headroom=rsi,
        foreign_flow_ratio=flow,
        bb_squeeze=bb,
        bci=bci,
    )


def _build_derived_feature_policy(
    raw: dict[str, Any],
    default: AccumulationDerivedFeaturePolicy,
) -> AccumulationDerivedFeaturePolicy:
    return AccumulationDerivedFeaturePolicy(
        rsi_period=_positive_i(raw, "rsi_period", default.rsi_period),
        trend_sma_period=_positive_i(raw, "trend_sma_period", default.trend_sma_period),
        trend_threshold_pct=_f(raw, "trend_threshold_pct", default.trend_threshold_pct),
        bb_period=_positive_i(raw, "bb_period", default.bb_period),
        bb_history=_positive_i(raw, "bb_history", default.bb_history),
        market_vwap_period=_positive_i(raw, "market_vwap_period", default.market_vwap_period),
        resistance_ma_period=_positive_i(raw, "resistance_ma_period", default.resistance_ma_period),
        resistance_high_period=_positive_i(
            raw, "resistance_high_period", default.resistance_high_period
        ),
        insider_lookback_days=_positive_i(
            raw, "insider_lookback_days", default.insider_lookback_days
        ),
    )
