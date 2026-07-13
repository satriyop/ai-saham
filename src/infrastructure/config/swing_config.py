"""
Swing workflow calibration config — compatibility facade.

Re-exports from application DTO and infrastructure loader.
Kept for backward compatibility; prefer direct imports where possible.

Layer: Infrastructure

Compatibility surface:
- Canonical import(s):
  - SetupTargetConfig, SwingConfig -> src.application.dto.swing_config
  - load_swing_config -> src.infrastructure.config.swing_config_loader
- Allowed contents:
  - imports and __all__ only. No new implementation may be added here.
- Expiry:
  - permanent public API; remove only after adapter/test imports migrate to
    the canonical modules above.
"""

from src.application.dto.swing_config import SetupTargetConfig, SwingConfig
from src.infrastructure.config.swing_config_loader import load_swing_config

__all__ = ["SetupTargetConfig", "SwingConfig", "load_swing_config"]
