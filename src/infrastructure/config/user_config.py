"""
Backward-compatible shim — delegates to AppConfig so existing call sites keep working.

config/user.yaml values now flow through the unified merge pipeline in app_config.py.
"""

from src.infrastructure.config.app_config import APP_CFG


def get_swing_default(key: str, fallback=None):
    """Return swing.<key> from the merged config (default.yaml + user.yaml)."""
    return getattr(APP_CFG.swing, key, fallback)
