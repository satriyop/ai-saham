"""
Archived signal config warning policy.

Warns when the archived six-factor signal config (baseline/diagnostic-only)
is authored away from its defaults, since it no longer tunes canonical staged
evidence scoring. Pure; no engine construction, no infrastructure wiring.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

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
