"""
Pre-open screener config loader.

Layer: Infrastructure
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.infrastructure.config.app_config import APP_CFG

PRE_OPEN_CONFIG_PATH = Path(APP_CFG.config_paths.pre_open_screener)


def load_pre_open_screen_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> PreOpenScreenConfig:
    """Load pre-open screener config and apply CLI-level overrides."""
    path = config_path or PRE_OPEN_CONFIG_PATH
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        config = PreOpenScreenConfig.from_yaml(data)
    else:
        config = PreOpenScreenConfig()

    return apply_pre_open_overrides(config, overrides or {})


def apply_pre_open_overrides(
    config: PreOpenScreenConfig,
    overrides: dict[str, Any],
) -> PreOpenScreenConfig:
    """Apply parsed adapter overrides to the mutable config object."""
    if overrides.get("iev_min") is not None:
        config.iev_min = int(overrides["iev_min"])
    if overrides.get("iep_min") is not None:
        config.iep_min = int(overrides["iep_min"])
    if overrides.get("capital") is not None:
        config.capital = Decimal(str(overrides["capital"]))
    if overrides.get("stop_loss_pct") is not None:
        config.stop_loss_pct = Decimal(str(overrides["stop_loss_pct"]))
    if overrides.get("tick_above") is not None:
        config.tick_above = int(overrides["tick_above"])
    if overrides.get("top_n") is not None:
        config.top_n = int(overrides["top_n"])
    if overrides.get("fast_mode") is not None:
        config.fast_mode = bool(overrides["fast_mode"])
    if overrides.get("max_gap") is not None:
        config.max_gap_pct = Decimal(str(overrides["max_gap"]))
    if overrides.get("atr_mult") is not None:
        config.atr_multiplier = Decimal(str(overrides["atr_mult"]))

    return config
