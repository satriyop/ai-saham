"""
Parser for setup target configurations.

Layer: Infrastructure
"""

from decimal import Decimal
from typing import Any

from src.application.dto.swing_config import SetupTargetConfig, SwingConfig


def parse_setup_targets(raw: Any, defaults: SwingConfig) -> dict[str, SetupTargetConfig]:
    if not isinstance(raw, dict):
        return defaults.setup_targets
    parsed: dict[str, SetupTargetConfig] = {}
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        parsed[str(key).lower()] = SetupTargetConfig(
            take_profit_pct=Decimal(str(val["take_profit_pct"])),
            stop_loss_pct=Decimal(str(val["stop_loss_pct"])),
        )
    return parsed if parsed else defaults.setup_targets
