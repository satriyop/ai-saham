"""User-local CLI defaults loaded from config/user.yaml (gitignored)."""

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parents[4] / "config" / "user.yaml"
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                _cache = yaml.safe_load(f) or {}
        else:
            _cache = {}
    return _cache


def get_swing_default(key: str, fallback=None):
    """Return swing.<key> from config/user.yaml, or fallback if absent."""
    return _load().get("swing", {}).get(key, fallback)
