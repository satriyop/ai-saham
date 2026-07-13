"""
Shared engine config loading.

Loads a YAML engine config file.

Layer: Infrastructure
"""

from pathlib import Path

import yaml


def load_engine_config(path: Path) -> dict:
    """Load a YAML engine config file. Returns empty dict if file is absent."""
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}
