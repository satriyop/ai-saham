"""
YAML implementation of UniverseConfigLoader.

Layer: Infrastructure
"""

from pathlib import Path

import yaml

from src.application.ports.universe_config_loader import UniverseConfigLoader


class YamlUniverseConfigLoader(UniverseConfigLoader):
    """Loads universe configurations from YAML files."""

    def load_config(self, path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(
                f"Universe config not found at '{path}'. Run: saham fetch universe update"
            )
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
