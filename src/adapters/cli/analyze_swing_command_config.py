"""
Shared swing command configuration and setup-catalog helper.

Neutral adapter module: both analyze_swing_commands.py (`saham analyze
swing`) and analyze_swing_compare_commands.py (`saham analyze
swing-compare`) import config and the setup catalog builder from here.
Neither command module owns the other's dependencies.

Layer: Adapter
"""

from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.evaluate_swing_setup_use_case import SwingSetupCatalogConfig
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.analyze_swing_config import load_analyze_swing_config
from src.infrastructure.config.swing_backtest_config import load_swing_backtest_config
from src.infrastructure.config.swing_config import load_swing_config

# Load split swing workflow config; fall back to typed defaults on any error.
SWING_CONFIG = load_swing_config()
SWING_BACKTEST_CONFIG = load_swing_backtest_config()
ANALYZE_SWING_CONFIG = load_analyze_swing_config()
ACCUMULATION_SCREENER_CONFIG = load_accumulation_screener_config()


def setup_config() -> SwingSetupCatalogConfig:
    return build_swing_setup_catalog_config(SWING_CONFIG)
