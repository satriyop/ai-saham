"""
Signal engine raw config loading.

Reads signal_engine.yaml from the path configured in AppConfig and returns the
raw dict. Application resolvers stay pure by consuming this raw dict instead
of reading files themselves.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.engine_config_loader import load_engine_config


def load_signal_engine_config_raw() -> dict:
    """Load the raw signal_engine.yaml config as a dict."""
    return load_engine_config(Path(load_app_config().config_paths.signal_engine))
