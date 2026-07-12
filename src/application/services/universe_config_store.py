"""YAML config persistence for universe management.

Layer: Application
"""

from pathlib import Path

import yaml


class UniverseConfigStore:
    """Handles loading and saving universe YAML configuration."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    @property
    def config_path(self) -> Path:
        return self._config_path

    def load_raw(self) -> dict:
        """Load config as raw dict. Returns empty dict if file missing/unreadable."""
        if not self._config_path.exists():
            return {}
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_raw(self, data: dict, *, updated: str) -> None:
        """Save config with exact header format and sorted keys."""
        header = (
            "# IDX Stock Universe Lists\n"
            "#\n"
            "# These lists are used by `saham fetch market` and `saham screen accum`\n"
            "# to define which tickers to scan.\n"
            "#\n"
            "# IDX rebalances LQ45 and IDX80 every February and August.\n"
            "# Auto-updated via: saham fetch universe update (Stockbit Exodus API)\n"
            "#\n"
            f"# Last updated: {updated}\n\n"
        )
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            f.write(header)
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=True)
