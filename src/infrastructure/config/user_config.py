"""
Backward-compatible shim — delegates to AppConfig so existing call sites keep working.

config/user.yaml values now flow through the unified merge pipeline in app_config.py.

Compatibility surface:
- Canonical import(s):
  - APP_CFG.swing.<key> -> src.infrastructure.config.app_config
- Allowed contents:
  - this single delegation function only. No other user config helpers may be
    added to this compatibility surface.
- Expiry:
  - permanent public API unless all call sites migrate to APP_CFG.swing
    directly.
"""

from src.infrastructure.config.app_config import APP_CFG

__all__ = ["get_swing_default"]


def get_swing_default(key: str, fallback=None):
    """Return swing.<key> from the merged config (default.yaml + user.yaml)."""
    return getattr(APP_CFG.swing, key, fallback)
