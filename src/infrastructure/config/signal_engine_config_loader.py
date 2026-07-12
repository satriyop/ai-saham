"""
Signal engine raw config loading.

Reads signal_engine.yaml from the path configured in APP_CFG and returns the
raw dict. Application resolvers stay pure by consuming this raw dict instead
of reading files themselves.
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.engine_bootstrap.config_resolvers import (
    _load_engine_config,
)
from src.infrastructure.config.app_config import APP_CFG


def load_signal_engine_config_raw() -> dict:
    """Load the raw signal_engine.yaml config as a dict."""
    return _load_engine_config(Path(APP_CFG.config_paths.signal_engine))
