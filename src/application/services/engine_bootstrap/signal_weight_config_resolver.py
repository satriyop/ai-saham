"""
Signal engine weight config resolving.

Pure config normalization for signal factor weights: parses enabled factors,
renormalizes weights, and composes the (active, raw, config) tuple used by
signal-audit observability. No engine construction, no infrastructure wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.services.signal_engine_config import SignalEngineConfig


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


def resolve_signal_weight_tables(
    cfg: dict,
) -> "tuple[dict[str, float], dict[str, float], SignalEngineConfig]":
    """
    Resolve (active_weights, raw_weights, config) for signal-audit observability.

    active_weights: renormalized weights actually used by the current engine.
    raw_weights:    raw configured weights from YAML (pre-renormalization).
    config:         resolved SignalEngineConfig.

    Falls back to AssessSignalUseCase._DEFAULT_WEIGHTS when config is absent so the
    audit reflects the same weights the production engine would use. Pure mapping:
    accepts an already-loaded raw config dict, does not read files.
    """
    from src.application.services.engine_bootstrap.signal_scoring_config_resolver import (
        resolve_signal_engine_config,
    )
    from src.application.use_case.assess_signal_use_case import _DEFAULT_WEIGHTS

    active = _resolve_signal_weights(cfg) or dict(_DEFAULT_WEIGHTS)
    raw = _resolve_signal_raw_weights(cfg) or dict(_DEFAULT_WEIGHTS)
    signal_config = resolve_signal_engine_config(cfg)
    return active, raw, signal_config
