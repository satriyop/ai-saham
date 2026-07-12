"""Loader for institutional accumulation analysis config (Phase E).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.services.institutional_flow_config import (
    InstitutionalAccumulationConfig,
)

DEFAULT_INSTITUTIONAL_ACCUMULATION_CONFIG_PATH = Path("config/institutional_accumulation.yaml")


def load_institutional_accumulation_config(
    path: str | Path | None = None,
) -> InstitutionalAccumulationConfig:
    """Load InstitutionalAccumulationConfig from YAML file path.

    Falls back to pure application defaults when the default config path
    does not exist. An explicit path that does not exist raises
    FileNotFoundError.
    """
    if path is None:
        config_path = DEFAULT_INSTITUTIONAL_ACCUMULATION_CONFIG_PATH
        if not config_path.exists():
            return InstitutionalAccumulationConfig.from_mapping({})
    else:
        config_path = Path(path)

    with open(config_path, "r") as handle:
        raw = yaml.safe_load(handle) or {}
    return InstitutionalAccumulationConfig.from_mapping(raw)
