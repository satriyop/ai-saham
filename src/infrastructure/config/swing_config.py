"""
Swing workflow calibration config — compatibility facade.

Re-exports from application DTO and infrastructure loader.
Kept for backward compatibility; prefer direct imports where possible.

Layer: Infrastructure
"""

from src.application.dto.swing_config import SetupTargetConfig, SwingConfig
from src.infrastructure.config.swing_config_loader import load_swing_config

__all__ = ["SetupTargetConfig", "SwingConfig", "load_swing_config"]
