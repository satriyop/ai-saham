"""
Shared engine config loading.

Loads a YAML engine config file. Used by both the signal engine and risk
engine config resolvers, and by the risk/signal engine factories.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_engine_config(path: Path) -> dict:
    """Load a YAML engine config file. Returns empty dict if file is absent."""
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}
